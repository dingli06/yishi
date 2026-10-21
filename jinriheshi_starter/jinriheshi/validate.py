from __future__ import annotations

from collections import Counter
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .common import digest, read_json, safe_local_path


@lru_cache(maxsize=32)
def _validator(path: str, modified_ns: int):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise RuntimeError("Install development dependencies: python -m pip install -r requirements-dev.txt") from exc
    schema = read_json(Path(path))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def schema_errors(root: Path, filename: str, value: Any) -> list[str]:
    path = root / "schemas" / filename
    validator = _validator(str(path.resolve()), path.stat().st_mtime_ns)
    errors = validator.iter_errors(value)
    return [f"{'/'.join(map(str, e.absolute_path)) or '$'}: {e.message}"
            for e in sorted(errors, key=lambda e: str(list(e.absolute_path)))]


def dictionary_errors(root: Path) -> list[str]:
    errors = []
    for filename, prefix in [("ingredients.json", "ing_"), ("equipment.json", "eq_")]:
        dictionary = read_json(root / "data/dictionaries" / filename)
        seen_ids: set[str] = set()
        aliases: dict[str, str] = {}
        for item in dictionary["items"]:
            identifier = item["id"]
            if identifier in seen_ids or not identifier.startswith(prefix):
                errors.append(f"{filename}: duplicate/invalid id {identifier}")
            seen_ids.add(identifier)
            for term in [item["name"], *item.get("aliases", [])]:
                if term in aliases and aliases[term] != identifier:
                    errors.append(f"{filename}: ambiguous alias {term}")
                aliases[term] = identifier
        if filename == "ingredients.json":
            for item in dictionary["items"]:
                for component in item.get("components", []):
                    if component not in seen_ids:
                        errors.append(f"{item['id']}: unresolved component {component}")
    return errors


def validate_request(root: Path, request: dict[str, Any]) -> list[str]:
    errors = schema_errors(root, "recommendation_request.schema.json", request)
    if errors:
        return errors
    ingredients = {i["id"] for i in read_json(root / "data/dictionaries/ingredients.json")["items"]}
    equipment = {i["id"] for i in read_json(root / "data/dictionaries/equipment.json")["items"]}
    tags = read_json(root / "data/dictionaries/tags.json")["items"]
    groups = {name: {i["id"] for i in tags if i["group"] == name} for name in ("tastes", "cuisines", "textures")}
    constraints = request.get("constraints", {})
    preferences = request.get("preferences", {})
    checks = [(f"constraints.{key}", constraints.get(key, []), ingredients)
              for key in ("owned_ingredients", "required_ingredients", "excluded_ingredients")]
    checks += [("constraints.available_equipment", constraints.get("available_equipment") or [], equipment),
               ("constraints.cuisines_only", constraints.get("cuisines_only", []), groups["cuisines"]),
               ("preferences.priority_ingredients", preferences.get("priority_ingredients", []), ingredients)]
    checks += [(f"preferences.{key}", preferences.get(key, []), groups[key]) for key in groups]
    for field, values, allowed in checks:
        unknown = set(values) - allowed
        if unknown:
            errors.append(f"{field}: unknown IDs {sorted(unknown)}")
    if set(constraints.get("required_ingredients", [])).intersection(constraints.get("excluded_ingredients", [])):
        errors.append("An ingredient cannot be both required and excluded")
    if constraints.get("pantry_mode") == "allow_missing" and constraints.get("max_missing_ingredients") is None:
        errors.append("allow_missing requires max_missing_ingredients")
    return errors


def validate_records(root: Path, recipes: list[dict[str, Any]]) -> list[str]:
    errors = dictionary_errors(root)
    ingredients = {x["id"] for x in read_json(root / "data/dictionaries/ingredients.json")["items"]}
    equipment = {x["id"] for x in read_json(root / "data/dictionaries/equipment.json")["items"]}
    tag_items = read_json(root / "data/dictionaries/tags.json")["items"]
    tag_groups = {name: {i["id"] for i in tag_items if i["group"] == name} for name in ("tastes", "cuisines", "textures")}
    seen_ids: set[tuple[str, str]] = set()
    for recipe in recipes:
        label = recipe.get("title", "<untitled>")
        structural = schema_errors(root, "recipe.schema.json", recipe)
        if structural:
            errors.extend(f"{label}: {e}" for e in structural)
            continue
        key = (recipe["recipe_id"], recipe["recipe_version"])
        if key in seen_ids:
            errors.append(f"{label}: duplicate recipe/version")
        seen_ids.add(key)
        raw_path = safe_local_path(root, recipe["source"]["raw_path"])
        if not raw_path.exists():
            errors.append(f"{label}: missing raw file")
            continue
        raw = raw_path.read_bytes()
        if digest(raw) != recipe["source"]["content_sha256"]:
            errors.append(f"{label}: changed raw bytes")
        text = raw.decode("utf-8")
        if recipe["source"]["source_id"] == "howtocook":
            if not re.fullmatch(r"[0-9a-f]{40}", recipe["source"]["revision"]):
                errors.append(f"{label}: HowToCook revision must be a pinned Git commit")
            if recipe["source"]["blob_sha"] is None:
                errors.append(f"{label}: HowToCook requires Git blob integrity metadata")
        evidence = list(recipe["tag_evidence"]) + list(recipe["equipment"]["evidence"])
        groups: Counter[str] = Counter()
        for item in recipe["ingredients"]:
            if item["ingredient_id"] not in ingredients:
                errors.append(f"{label}: unknown ingredient id {item['ingredient_id']}")
            evidence.extend(item["evidence"])
            if item["requirement"] == "alternative":
                if not item["alternative_group"]:
                    errors.append(f"{label}: alternative ingredient without group")
                else:
                    groups[item["alternative_group"]] += 1
            elif item["alternative_group"] is not None:
                errors.append(f"{label}: group only allowed on alternative ingredients")
        for group, count in groups.items():
            if count < 2:
                errors.append(f"{label}: alternative group {group} has fewer than two options")
        for item in evidence:
            if item["quote"] not in text:
                errors.append(f"{label}: evidence quote not present: {item['quote'][:65]!r}")
        for key in ("tastes", "cuisines", "textures"):
            for value in recipe["tags"][key]:
                if value not in tag_groups[key]:
                    errors.append(f"{label}: unknown {key} tag {value}")
                if not any(e["field"] == "tags." + key and e["value"] == value for e in recipe["tag_evidence"]):
                    errors.append(f"{label}: {key}/{value} tag lacks evidence")
        equip = recipe["equipment"]
        for identifier in equip["required_all"] + [v for group in equip["required_any"] for v in group]:
            if identifier not in equipment:
                errors.append(f"{label}: unknown equipment {identifier}")
        if any(not group for group in equip["required_any"]):
            errors.append(f"{label}: empty equipment alternative group")
        for key in ("total_minutes", "active_minutes", "source_estimate_minutes"):
            value = recipe["time"][key]
            if value is not None and value["min"] > value["max"]:
                errors.append(f"{label}: inverted {key} interval")
        if recipe["time"]["status"] == "verified":
            if recipe["time"]["total_minutes"] is None or not recipe["review"]["cooking_tested"]:
                errors.append(f"{label}: verified time requires full interval and cooking verification")
        elif recipe["time"]["total_minutes"] is not None or recipe["time"]["active_minutes"] is not None:
            errors.append(f"{label}: unaudited time belongs in source_estimate_minutes")
        if recipe["publication"]["state"] == "published":
            publication = recipe["publication"]
            if (recipe["review"]["status"] != "approved" or not publication["reviewed_by"] or
                    not publication["reviewed_at"] or publication["reviewed_by"].startswith("agent:")):
                errors.append(f"{label}: published recipe lacks human publication approval")
            if not recipe["content"]["steps"] or not recipe["ingredients"]:
                errors.append(f"{label}: published recipe lacks executable content")
    return errors


def validate_dataset(root: Path) -> dict[str, Any]:
    from .storage import JsonRecipeRepository
    recipes = list(JsonRecipeRepository(root / "data/generated/recipes.jsonl").all())
    errors = validate_records(root, recipes)
    for path in sorted((root / "examples").glob("request_*.json")):
        errors.extend(f"{path.name}: {e}" for e in validate_request(root, read_json(path)))
    for path in sorted((root / "examples").glob("event_*.json")):
        errors.extend(f"{path.name}: {e}" for e in schema_errors(root, "event.schema.json", read_json(path)))
    for path in sorted((root / "examples").glob("response_*.json")):
        errors.extend(f"{path.name}: {e}" for e in schema_errors(root, "recommendation_response.schema.json", read_json(path)))
    return {"ok": not errors, "recipe_count": len(recipes), "errors": errors,
            "checks": ["JSON Schema Draft 2020-12", "source SHA256", "exact evidence quotes",
                       "dictionary references", "alternative groups", "publication gates",
                       "time bounds and verification state", "example request/event contracts"]}
