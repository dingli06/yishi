from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Any, Iterable


def ingredient_conflict(identifier: str, exclusions: set[str],
                        dictionary: dict[str, dict[str, Any]], seen: set[str] | None = None) -> bool:
    """未知复合调料成分不能用于断言符合排除要求。"""
    if not exclusions:
        return False
    if identifier in exclusions:
        return True
    seen = set(seen or ())
    if identifier in seen:
        return True
    seen.add(identifier)
    item = dictionary.get(identifier)
    if not item or item.get("component_status") == "unknown":
        return True
    return any(ingredient_conflict(c, exclusions, dictionary, seen) for c in item.get("components", []))


def ingredient_selection(recipe: dict[str, Any], constraints: dict[str, Any],
                         dictionary: dict[str, dict[str, Any]]) -> tuple[list[str], set[str], set[str], set[str]]:
    """返回失败原因、实际选中、缺失、明确省略的可选材料；库存仅核对种类。"""
    pantry = constraints.get("pantry_mode", "any")
    owned = set(constraints.get("owned_ingredients", []))
    excluded = set(constraints.get("excluded_ingredients", []))
    must_use = set(constraints.get("required_ingredients", []))
    required: set[str] = set()
    selected: set[str] = set()
    omitted: set[str] = set()
    alternatives: dict[str, list[str]] = defaultdict(list)
    errors = []
    for item in recipe["ingredients"]:
        identifier = item["ingredient_id"]
        kind = item["requirement"]
        if kind == "unknown":
            errors.append("ingredient_requirements_unknown")
            continue
        if kind == "alternative":
            alternatives[item["alternative_group"]].append(identifier)
            continue
        conflict = ingredient_conflict(identifier, excluded, dictionary)
        if kind == "optional":
            if conflict or (pantry != "any" and identifier not in owned and identifier not in must_use):
                omitted.add(identifier)
            else:
                selected.add(identifier)
                if identifier in must_use:
                    required.add(identifier)
        else:
            if conflict:
                errors.append("excluded_ingredient_or_unknown_component")
            required.add(identifier)
            selected.add(identifier)
    for group in alternatives.values():
        allowed = [i for i in group if not ingredient_conflict(i, excluded, dictionary)]
        if not allowed:
            errors.append("excluded_ingredient_or_unknown_component")
            continue
        # 候选版本的替代组由审核数据提供；不在推荐时发明替代配方。
        chosen = sorted(allowed, key=lambda i: (i not in must_use, i not in owned, i))[0]
        required.add(chosen)
        selected.add(chosen)
    missing = required - owned
    if must_use - selected:
        errors.append("required_ingredient_missing")
    if pantry == "only_owned" and missing:
        errors.append("pantry_missing")
    if pantry == "allow_missing":
        limit = constraints.get("max_missing_ingredients")
        if limit is None:
            errors.append("missing_purchase_limit")
        elif len(missing) > limit:
            errors.append("purchase_limit_exceeded")
    return errors, selected, missing, omitted


def evaluate(recipe: dict[str, Any], request: dict[str, Any], mode: str,
             dictionary: dict[str, dict[str, Any]]) -> dict[str, Any]:
    constraints = request.get("constraints", {})
    preferences = request.get("preferences", {})
    context = request.get("context", {})
    errors: list[str] = []
    notices: list[str] = []
    state = recipe["publication"]["state"]
    if state != "published" and not (mode == "development" and state == "development"):
        return {"errors": ["not_published"], "recipe": recipe}
    if state == "published":
        publication = recipe["publication"]
        if (recipe["review"]["status"] != "approved" or not publication.get("reviewed_by") or
                not publication.get("reviewed_at") or publication["reviewed_by"].startswith("agent:")):
            return {"errors": ["publication_review_missing"], "recipe": recipe}
    if not recipe["content"]["steps"]:
        errors.append("content_incomplete")
    if recipe["dish_id"] in context.get("seen_dish_ids", []):
        errors.append("already_seen")
    needs_ingredient_check = bool(constraints.get("excluded_ingredients") or constraints.get("required_ingredients") or
                                 constraints.get("pantry_mode", "any") != "any")
    approved_ingredient_status = {"verified"} if mode == "production" else {"verified", "agent_checked"}
    ingredient_complete = recipe["review"]["ingredient_completeness"] in approved_ingredient_status
    if needs_ingredient_check and not ingredient_complete:
        errors.append("ingredients_not_reviewed")
    ingredient_errors, selected, missing, omitted = ingredient_selection(recipe, constraints, dictionary)
    if needs_ingredient_check:
        errors.extend(ingredient_errors)
    elif ingredient_errors:
        notices.append("配料结构仍有待审核项，请以完整原文核对。")
    equipment = constraints.get("available_equipment")
    if equipment is not None:
        permitted = {"verified"} if mode == "production" else {"verified", "agent_checked"}
        if recipe["equipment"]["status"] not in permitted:
            errors.append("equipment_unknown")
        else:
            owned_equipment = set(equipment)
            if not set(recipe["equipment"]["required_all"]).issubset(owned_equipment):
                errors.append("equipment_missing")
            if any(not set(group).intersection(owned_equipment) for group in recipe["equipment"]["required_any"]):
                errors.append("equipment_alternative_missing")
    deadline = constraints.get("max_total_minutes")
    if deadline is not None:
        timing = recipe["time"]
        if (timing["status"] != "verified" or timing["total_minutes"] is None or
                not recipe["review"]["cooking_tested"]):
            errors.append("total_time_unverified")
        elif timing["total_minutes"]["max"] > deadline:
            errors.append("deadline_exceeded")
        # 前提即便在development模式也不能被source_estimate绕过。
        if set(timing["prerequisites"]) - set(constraints.get("confirmed_prerequisites", [])):
            errors.append("prerequisite_unconfirmed")
    cuisines_only = set(constraints.get("cuisines_only", []))
    if cuisines_only and not cuisines_only.intersection(recipe["tags"]["cuisines"]):
        errors.append("cuisine_not_matched")
    forms = constraints.get("meal_forms", [])
    if forms and recipe["tags"]["meal_form"] not in forms:
        errors.append("meal_form_not_matched")
    standalone = constraints.get("standalone_meal")
    if standalone is not None and recipe["tags"]["standalone_meal"] is not standalone:
        errors.append("standalone_meal_unknown_or_not_matched")
    servings = constraints.get("servings")
    if servings is not None:
        yields = recipe["servings"]
        if yields["status"] != "verified" or yields["min"] is None or yields["max"] is None:
            errors.append("servings_unverified")
        elif not yields["min"] <= servings <= yields["max"]:
            errors.append("servings_out_of_range")
    score = 1.0
    reasons = []
    for key, weight, label in [("tastes", 3, "口味"), ("cuisines", 3, "菜系"), ("textures", 1, "口感")]:
        hits = sorted(set(preferences.get(key, [])).intersection(recipe["tags"][key]))
        if hits:
            score += len(hits) * weight
            reasons.append(f"符合你选择的{label}偏好。")
    priority = sorted(set(preferences.get("priority_ingredients", [])).intersection(selected))
    if priority:
        score += 2 * len(priority)
        reasons.append("可以使用你想用掉的食材：" + "、".join(dictionary.get(i, {}).get("name", i) for i in priority))
    novelty = preferences.get("novelty", "any")
    if recipe["dish_id"] in context.get("favorite_dish_ids", []) and novelty == "familiar":
        score += 3
        reasons.append("来自你收藏过的菜品。")
    if recipe["dish_id"] in context.get("recently_cooked_dish_ids", []):
        score -= 2 if novelty == "new" else 0.5
    if constraints.get("pantry_mode", "any") != "any" and ingredient_complete and not missing:
        reasons.append("必需食材种类已匹配；数量请自行核对。")
    if deadline is not None and "total_time_unverified" not in errors and "deadline_exceeded" not in errors:
        reasons.append("已核验的总耗时满足本次时间上限。")
    if not reasons:
        reasons.append("从符合当前条件的候选中随机选出。")
    if recipe["time"]["status"] != "verified":
        notices.append("源文时间仅供参考，尚未核验完整开饭时间。")
    if recipe["time"]["prerequisites"]:
        notices.append("前置条件：" + "；".join(recipe["time"]["prerequisites"]))
    if recipe["tags"]["standalone_meal"] is False:
        notices.append("这是一道菜或配餐部分，需按需要另配主食或其他菜。")
    return {"errors": sorted(set(errors)), "score": max(0.1, score), "reasons": reasons[:3],
            "selected": selected, "missing": missing, "omitted": omitted,
            "notices": notices, "recipe": recipe}


def recommend(recipes: Iterable[dict[str, Any]], request: dict[str, Any],
              dictionary: dict[str, dict[str, Any]], *, mode: str = "production",
              seed: int | None = None) -> dict[str, Any]:
    if mode not in {"production", "development"}:
        raise ValueError("Unsupported mode")
    if mode == "production" and seed is not None:
        raise ValueError("Fixed random seeds are for development only")
    outcomes = [evaluate(recipe, request, mode, dictionary) for recipe in recipes]
    excluded = Counter(error for outcome in outcomes for error in outcome["errors"])
    # 每个菜品只占一个抽签位置，避免一个菜的多个版本增加抽中概率。
    by_dish: dict[str, dict[str, Any]] = {}
    for outcome in sorted((o for o in outcomes if not o["errors"]),
                          key=lambda o: (-o["score"], o["recipe"]["recipe_id"], o["recipe"]["recipe_version"])):
        by_dish.setdefault(outcome["recipe"]["dish_id"], outcome)
    candidates = list(by_dish.values())
    notices = (["开发预览使用代理整理的种子数据，未经人工发布审核和实烹。"] if mode == "development" else [])
    result: dict[str, Any] = {"schema_version": "1.0.0", "mode": mode,
                              "status": "ok" if candidates else "no_candidate",
                              "candidate_count": len(candidates), "selected": None,
                              "exclusion_counts": dict(sorted(excluded.items())),
                              "suggestions": [], "notices": notices}
    if not candidates:
        if mode == "production" and not any(
                o["recipe"]["publication"]["state"] == "published" and
                "publication_review_missing" not in o["errors"] for o in outcomes):
            result["suggestions"].append({"code": "NO_PUBLISHED_CONTENT", "message": "当前可发布内容不足；需要完成内容审核后再上线。"})
        if excluded.get("total_time_unverified"):
            result["suggestions"].append({"code": "TIME_DATA_UNVERIFIED", "message": "现有候选缺少已核验总时间；可明确取消严格时间条件或补充审核。"})
        elif excluded.get("deadline_exceeded"):
            result["suggestions"].append({"code": "RELAX_TIME", "message": "可选择放宽时间上限。"})
        if excluded.get("pantry_missing") or excluded.get("purchase_limit_exceeded"):
            result["suggestions"].append({"code": "ALLOW_PURCHASE", "message": "可选择允许补买食材；当前条件没有自动改变。"})
        if excluded.get("cuisine_not_matched"):
            result["suggestions"].append({"code": "RELAX_CUISINE", "message": "可选择放宽菜系。"})
        if excluded.get("already_seen"):
            result["suggestions"].append({"code": "START_NEW_SESSION", "message": "可明确开启新一轮，重新允许看过的菜。"})
        return result
    rng = random.Random(seed) if seed is not None else random.SystemRandom()
    # 先洗牌再稳定按分数排序；同分边界不会永久排除固定ID之外的候选。
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    shortlist = sorted(shuffled, key=lambda o: -o["score"])[:20]
    chosen = rng.choices(shortlist, weights=[o["score"] for o in shortlist], k=1)[0]
    recipe = chosen["recipe"]
    pantry_checked = request.get("constraints", {}).get("pantry_mode", "any") != "any"
    result["selected"] = {
        "recipe_id": recipe["recipe_id"], "recipe_version": recipe["recipe_version"],
        "dish_id": recipe["dish_id"], "title": recipe["title"],
        "publication_state": recipe["publication"]["state"], "review_status": recipe["review"]["status"],
        "source_url": recipe["source"]["url"],
        "source_estimate_minutes": recipe["time"]["source_estimate_minutes"],
        "total_minutes": recipe["time"]["total_minutes"], "time_status": recipe["time"]["status"],
        "meal_form": recipe["tags"]["meal_form"], "standalone_meal": recipe["tags"]["standalone_meal"],
        "selected_ingredient_ids": sorted(chosen["selected"]),
        "missing_ingredient_ids": sorted(chosen["missing"]) if pantry_checked else None,
        "omitted_optional_ingredient_ids": sorted(chosen["omitted"]),
        "pantry_match_scope": "ingredient_types_only" if pantry_checked else "not_checked",
        "reasons": chosen["reasons"], "notices": chosen["notices"],
    }
    return result
