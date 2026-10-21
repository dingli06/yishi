"""真实数据的来源/结构验证，以及可能破坏可追溯性的工程边界。"""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from jinriheshi.build import build
from jinriheshi.common import read_json, root_path
from jinriheshi.sqlite_export import export_sqlite
from jinriheshi.storage import JsonRecipeRepository, SqliteRecipeRepository
from jinriheshi.validate import schema_errors, validate_dataset, validate_records, validate_request

ROOT = root_path()


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT / "data/generated/build_report.json").exists():
            build(ROOT)
        cls.recipes = list(JsonRecipeRepository(ROOT / "data/generated/recipes.jsonl").all())
        cls.seed = list(JsonRecipeRepository(ROOT / "data/generated/seed_recipes.jsonl").all())

    def test_actual_dataset_passes_structure_evidence_and_references(self):
        result = validate_dataset(ROOT)
        self.assertTrue(result["ok"], result["errors"][:10])
        self.assertEqual(result["recipe_count"], 372)
        self.assertEqual(len(self.seed), 30)

    def test_actual_seed_never_claims_production_or_tested_time(self):
        for recipe in self.seed:
            self.assertEqual(recipe["publication"]["state"], "development")
            self.assertIsNone(recipe["publication"]["reviewed_by"])
            self.assertFalse(recipe["review"]["cooking_tested"])
            self.assertIsNone(recipe["time"]["total_minutes"])
            self.assertIsNone(recipe["time"]["active_minutes"])

    def test_build_is_byte_reproducible(self):
        names = ["recipes.jsonl", "seed_recipes.jsonl", "catalog.json", "build_report.json"]
        build(ROOT)
        before = {name: (ROOT / "data/generated" / name).read_bytes() for name in names}
        build(ROOT)
        after = {name: (ROOT / "data/generated" / name).read_bytes() for name in names}
        self.assertEqual(before, after)

    def test_stale_overlay_revision_fails_before_any_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data/sources").mkdir(parents=True)
            (root / "data/overlays").mkdir(parents=True)
            (root / "data/generated").mkdir(parents=True)
            (root / "data/sources/howtocook.lock.json").write_text('{"revision":"new"}')
            (root / "data/overlays/howtocook_seed.json").write_text('{"source_revision":"old","recipes":[]}')
            marker = root / "data/generated/build_report.json"
            marker.write_text("sentinel")
            with self.assertRaisesRegex(ValueError, "stale"):
                build(root)
            self.assertEqual(marker.read_text(), "sentinel")

    def test_fabricated_evidence_is_rejected(self):
        recipe = copy.deepcopy(self.seed[0])
        recipe["ingredients"][0]["evidence"][0]["quote"] = "TEST-ONLY-NOT-IN-SOURCE-728835"
        errors = validate_records(ROOT, [recipe])
        self.assertTrue(any("evidence quote not present" in error for error in errors))

    def test_unknown_excluded_ingredient_is_an_error(self):
        request = {"schema_version": "1.0.0", "constraints": {"excluded_ingredients": ["ing_typo"]}}
        self.assertTrue(any("unknown IDs" in e for e in validate_request(ROOT, request)))

    def test_conflicting_requirement_is_an_error(self):
        request = {"schema_version": "1.0.0", "constraints": {"required_ingredients": ["ing_egg"], "excluded_ingredients": ["ing_egg"]}}
        self.assertTrue(validate_request(ROOT, request))

    def test_unknown_equipment_or_tags_are_errors(self):
        for request in [
            {"schema_version": "1.0.0", "constraints": {"available_equipment": ["eq_typo"]}},
            {"schema_version": "1.0.0", "preferences": {"cuisines": ["cuisine_typo"]}},
        ]:
            self.assertTrue(validate_request(ROOT, request))

    def test_event_permanent_rejection_requires_target_and_confirmation(self):
        event = read_json(ROOT / "examples/event_permanent_reject.json")
        self.assertFalse(schema_errors(ROOT, "event.schema.json", event))
        for field, value in [("confirmed_permanent", False), ("permanent_excluded_ingredient_ids", [])]:
            malformed = copy.deepcopy(event)
            malformed[field] = value
            self.assertTrue(schema_errors(ROOT, "event.schema.json", malformed))

    def test_accept_event_cannot_silently_become_permanent_exclusion(self):
        event = read_json(ROOT / "examples/event_accept.json")
        self.assertFalse(schema_errors(ROOT, "event.schema.json", event))
        event["scope"] = "permanent"
        self.assertTrue(schema_errors(ROOT, "event.schema.json", event))

    def test_missing_or_tampered_build_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recipes.jsonl"
            path.write_text('{}\n')
            with self.assertRaises(ValueError):
                JsonRecipeRepository(path)
            (path.parent / "build_report.json").write_text('{"files":{"recipes.jsonl":"wrong"}}')
            with self.assertRaises(ValueError):
                JsonRecipeRepository(path)

    def test_sqlite_roundtrip_and_rebuild_preserve_domain_records(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "recipes.sqlite"
            export_sqlite(ROOT, output)
            records = list(SqliteRecipeRepository(output).all())
            self.assertEqual(records, list(JsonRecipeRepository(ROOT / "data/generated/recipes.jsonl").all()))
            first = records[0]
            self.assertEqual(SqliteRecipeRepository(output).get(first["recipe_id"], first["recipe_version"]), first)
            export_sqlite(ROOT, output)
            self.assertEqual(len(list(SqliteRecipeRepository(output).all())), 372)

    def test_export_never_replaces_unmanaged_or_non_database_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "business.sqlite"
            with sqlite3.connect(output) as conn:
                conn.execute("CREATE TABLE important(value TEXT)")
            conn.close()
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                export_sqlite(ROOT, output)
            self.assertEqual(before, output.read_bytes())
            other = Path(directory) / "notes.json"
            other.write_text("keep")
            with self.assertRaises(ValueError):
                export_sqlite(ROOT, other)
            self.assertEqual(other.read_text(), "keep")

    def test_public_contract_excludes_runtime_bypass_parameters(self):
        api = read_json(ROOT / "contracts/openapi.json")
        create = api["paths"]["/v1/sessions"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(set(create["properties"]), {"constraints", "preferences"})
        public = api["components"]["schemas"]["PublicRecipe"]
        self.assertNotIn("publication", public["properties"])
        self.assertNotIn("review", public["properties"])
        self.assertNotIn("raw_path", public["properties"]["source"]["properties"])


if __name__ == "__main__":
    unittest.main()
