"""Recommendation contract tests with in-memory synthetic states.

Real HowToCook seeds are read only as structural templates. The ``TEST ONLY``
fixtures below simulate reviewed publication, measured time and servings solely
to exercise business rules; they are not reviewed or cooked real recipes and
are never written back to data/. Passing these tests is not a cooking audit.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from jinriheshi.recommend import ingredient_conflict, recommend


ROOT = Path(__file__).resolve().parents[1]


class RecommendationBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seeds = [json.loads(line) for line in
                     (ROOT / "data/generated/seed_recipes.jsonl").read_text(encoding="utf-8").splitlines()
                     if line.strip()]
        cls.dictionary = {item["id"]: item for item in json.loads(
            (ROOT / "data/dictionaries/ingredients.json").read_text(encoding="utf-8"))["items"]}
        cls.template = next(recipe for recipe in cls.seeds if recipe["title"] == "凉拌黄瓜")

    def recipe(self, number=1):
        """Return an explicitly fictional, schema-shaped fixture, never production data."""
        recipe = deepcopy(self.template)
        recipe.update(recipe_id=f"recipe_{number:032x}", dish_id=f"dish_{number:032x}",
                      recipe_version=f"rv_{number:024x}", title=f"TEST ONLY synthetic recipe {number}")
        recipe["publication"] = {"state": "published", "reviewed_by": "human:TEST_ONLY_FIXTURE",
                                 "reviewed_at": "2026-10-21T00:00:00Z"}
        recipe["review"] = {"status": "approved", "ingredient_completeness": "verified",
                            "issues": [], "reviewer": "human:TEST_ONLY_FIXTURE", "cooking_tested": False}
        recipe["ingredients"] = [self.ingredient("ing_tomato")]
        recipe["tags"] = {"tastes": [], "cuisines": [], "textures": [],
                          "meal_form": "dish", "standalone_meal": False}
        recipe["tag_evidence"] = []
        recipe["equipment"] = {"required_all": [], "required_any": [],
                               "status": "verified", "evidence": []}
        recipe["time"] = {"source_text": None, "source_estimate_minutes": None,
                          "total_minutes": None, "active_minutes": None,
                          "prerequisites": [], "status": "unknown"}
        recipe["servings"] = {"source_text": None, "min": None, "max": None,
                              "status": "unknown", "scaling_policy": "manual"}
        recipe["content"]["steps"] = [{"id": "test_step", "position": 1,
                                       "text": "TEST ONLY: simulated procedure; do not cook.",
                                       "source_heading": "TEST ONLY"}]
        recipe["extensions"]["test_only"] = True
        return recipe

    def ingredient(self, identifier, requirement="required", group=None):
        return {"ingredient_id": identifier, "source_name": self.dictionary[identifier]["name"],
                "role": "main", "requirement": requirement, "quantity_text": None,
                "alternative_group": group,
                "evidence": [{"quote": "TEST ONLY synthetic ingredient requirement", "section": "ingredients"}]}

    @staticmethod
    def request(*, constraints=None, preferences=None, context=None):
        return {"schema_version": "1.0.0", "constraints": constraints or {},
                "preferences": preferences or {}, "context": context or {}}

    def run_recommend(self, recipes, request=None, **kwargs):
        return recommend(recipes, request or self.request(), self.dictionary, **kwargs)

    def assert_no_candidate(self, result, reason=None):
        self.assertEqual(result["status"], "no_candidate")
        self.assertEqual(result["candidate_count"], 0)
        self.assertIsNone(result["selected"])
        if reason:
            self.assertGreater(result["exclusion_counts"].get(reason, 0), 0, result)

    def test_default_production_does_not_publish_development_data(self):
        result = self.run_recommend(self.seeds)
        self.assertEqual(result["mode"], "production")
        self.assert_no_candidate(result, "not_published")

    def test_published_state_requires_review_and_human_publication_metadata(self):
        for missing in ("reviewed_by", "reviewed_at", "review_status", "human_reviewer"):
            with self.subTest(missing=missing):
                recipe = self.recipe()
                if missing == "review_status":
                    recipe["review"]["status"] = "needs_review"
                elif missing == "human_reviewer":
                    recipe["publication"]["reviewed_by"] = "agent:TEST_ONLY_FIXTURE"
                else:
                    recipe["publication"][missing] = None
                self.assert_no_candidate(self.run_recommend([recipe]))

    def test_explicit_development_preview_can_use_real_seeds(self):
        result = self.run_recommend(self.seeds, mode="development", seed=7)
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["candidate_count"], 0)
        self.assertEqual(result["selected"]["publication_state"], "development")
        self.assertTrue(result["notices"])

    def test_unknown_and_source_estimated_time_cannot_meet_deadline(self):
        request = self.request(constraints={"max_total_minutes": 15})
        for status, total in (("unknown", None), ("source_estimate", None),
                              ("source_estimate", {"min": 5, "max": 10}), ("verified", None),
                              ("verified", {"min": 5, "max": 10})):
            with self.subTest(status=status, total=total):
                recipe = self.recipe()
                recipe["time"].update(status=status, total_minutes=total,
                                      source_estimate_minutes={"min": 5, "max": 10})
                self.assert_no_candidate(self.run_recommend([recipe], request), "total_time_unverified")

    def test_deadline_uses_verified_upper_bound_and_confirmed_prerequisites(self):
        recipe = self.recipe()
        recipe["review"]["cooking_tested"] = True  # TEST ONLY simulated evidence state.
        recipe["time"].update(status="verified", total_minutes={"min": 10, "max": 25})
        request = self.request(constraints={"max_total_minutes": 15})
        self.assert_no_candidate(self.run_recommend([recipe], request), "deadline_exceeded")
        recipe["time"].update(total_minutes={"min": 10, "max": 15}, prerequisites=["TEST ONLY: rice already cooked"])
        self.assert_no_candidate(self.run_recommend([recipe], request), "prerequisite_unconfirmed")
        request["constraints"]["confirmed_prerequisites"] = ["TEST ONLY: rice already cooked"]
        self.assertEqual(self.run_recommend([recipe], request)["status"], "ok")

    def test_equipment_requires_all_items_and_one_from_each_alternative_group(self):
        recipe = self.recipe()
        recipe["equipment"].update(required_all=["eq_pan", "eq_knife"],
                                   required_any=[["eq_chopsticks", "eq_toothpick"], ["eq_bowl", "eq_plate"]])
        valid = ["eq_pan", "eq_knife", "eq_toothpick", "eq_plate"]
        request = self.request(constraints={"available_equipment": valid})
        self.assertEqual(self.run_recommend([recipe], request)["status"], "ok")
        request["constraints"]["available_equipment"] = [x for x in valid if x != "eq_knife"]
        self.assert_no_candidate(self.run_recommend([recipe], request), "equipment_missing")
        request["constraints"]["available_equipment"] = [x for x in valid if x != "eq_plate"]
        self.assert_no_candidate(self.run_recommend([recipe], request), "equipment_alternative_missing")
        recipe["equipment"]["status"] = "unknown"
        request["constraints"]["available_equipment"] = valid
        self.assert_no_candidate(self.run_recommend([recipe], request), "equipment_unknown")

    def test_only_owned_rejects_missing_required_but_allows_missing_optional(self):
        recipe = self.recipe()
        recipe["ingredients"] = [self.ingredient("ing_tomato"), self.ingredient("ing_egg")]
        request = self.request(constraints={"pantry_mode": "only_owned", "owned_ingredients": ["ing_tomato"]})
        self.assert_no_candidate(self.run_recommend([recipe], request), "pantry_missing")
        recipe["ingredients"][1]["requirement"] = "optional"
        result = self.run_recommend([recipe], request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selected"]["missing_ingredient_ids"], [])
        self.assertIn("ing_egg", result["selected"]["omitted_optional_ingredient_ids"])

    def test_alternative_ingredient_group_needs_one_available_choice(self):
        recipe = self.recipe()
        recipe["ingredients"] += [self.ingredient("ing_light_soy_sauce", "alternative", "test_sauce"),
                                   self.ingredient("ing_dark_soy_sauce", "alternative", "test_sauce")]
        request = self.request(constraints={"pantry_mode": "only_owned",
                                            "owned_ingredients": ["ing_tomato", "ing_dark_soy_sauce"]})
        result = self.run_recommend([recipe], request)
        self.assertEqual(result["status"], "ok")
        self.assertIn("ing_dark_soy_sauce", result["selected"]["selected_ingredient_ids"])
        self.assertNotIn("ing_light_soy_sauce", result["selected"]["selected_ingredient_ids"])
        request["constraints"]["owned_ingredients"] = ["ing_tomato"]
        self.assert_no_candidate(self.run_recommend([recipe], request), "pantry_missing")

    def test_unknown_composite_component_does_not_claim_exclusion_compliance(self):
        self.assertEqual(self.dictionary["ing_oyster_sauce"]["component_status"], "unknown")
        self.assertEqual(self.dictionary["ing_tomato"]["component_status"], "simple")
        self.assertTrue(ingredient_conflict("ing_oyster_sauce", {"ing_egg"}, self.dictionary))
        self.assertFalse(ingredient_conflict("ing_tomato", {"ing_egg"}, self.dictionary))
        safe = self.recipe(1)
        unresolved = self.recipe(2)
        unresolved["ingredients"] = [self.ingredient("ing_oyster_sauce")]
        result = self.run_recommend([safe, unresolved], self.request(constraints={"excluded_ingredients": ["ing_egg"]}))
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["selected"]["recipe_id"], safe["recipe_id"])
        self.assertEqual(result["exclusion_counts"]["excluded_ingredient_or_unknown_component"], 1)

    def test_multiple_versions_do_not_multiply_dish_candidates(self):
        first = self.recipe(1)
        version = self.recipe(2)
        version["dish_id"] = first["dish_id"]
        other = self.recipe(3)
        result = self.run_recommend([first, version, other], mode="development", seed=8)
        self.assertEqual(result["candidate_count"], 2)

    def test_seen_dishes_are_excluded_across_versions(self):
        seen = self.recipe(1)
        seen_version = self.recipe(2)
        seen_version["dish_id"] = seen["dish_id"]
        unseen = self.recipe(3)
        request = self.request(context={"seen_dish_ids": [seen["dish_id"]]})
        result = self.run_recommend([seen, seen_version, unseen], request)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["selected"]["dish_id"], unseen["dish_id"])
        self.assert_no_candidate(self.run_recommend([seen, seen_version], request), "already_seen")

    def test_development_random_seed_is_reproducible_and_production_rejects_it(self):
        recipes = [self.recipe(n) for n in range(1, 8)]
        first = self.run_recommend(recipes, mode="development", seed=20261021)
        second = self.run_recommend(recipes, mode="development", seed=20261021)
        self.assertEqual(first, second)
        with self.assertRaises(ValueError):
            self.run_recommend(recipes, mode="production", seed=20261021)

    def test_soft_preferences_cannot_override_a_hard_time_limit(self):
        preferred = self.recipe(1)
        preferred["review"]["cooking_tested"] = True  # TEST ONLY simulated evidence state.
        preferred["tags"]["tastes"] = ["taste_sour", "taste_sweet", "taste_spicy"]
        preferred["time"].update(status="verified", total_minutes={"min": 30, "max": 60})
        allowed = self.recipe(2)
        allowed["review"]["cooking_tested"] = True  # TEST ONLY simulated evidence state.
        allowed["time"].update(status="verified", total_minutes={"min": 5, "max": 10})
        request = self.request(constraints={"max_total_minutes": 15},
                               preferences={"tastes": ["taste_sour", "taste_sweet", "taste_spicy"],
                                            "priority_ingredients": ["ing_tomato"]})
        result = self.run_recommend([preferred, allowed], request)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["selected"]["recipe_id"], allowed["recipe_id"])

    def test_purchase_limit_counts_missing_required_ingredient_types(self):
        recipe = self.recipe()
        recipe["ingredients"] += [self.ingredient("ing_egg"), self.ingredient("ing_cucumber", "optional")]
        request = self.request(constraints={"pantry_mode": "allow_missing", "owned_ingredients": ["ing_tomato"],
                                            "max_missing_ingredients": 1})
        result = self.run_recommend([recipe], request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["selected"]["missing_ingredient_ids"], ["ing_egg"])
        request["constraints"]["max_missing_ingredients"] = 0
        self.assert_no_candidate(self.run_recommend([recipe], request), "purchase_limit_exceeded")

    def test_unknown_servings_cannot_satisfy_strict_diner_count(self):
        recipe = self.recipe()
        request = self.request(constraints={"servings": 2})
        self.assert_no_candidate(self.run_recommend([recipe], request), "servings_unverified")
        recipe["servings"].update(status="verified", min=1, max=2)
        self.assertEqual(self.run_recommend([recipe], request)["status"], "ok")
        request["constraints"]["servings"] = 3
        self.assert_no_candidate(self.run_recommend([recipe], request), "servings_out_of_range")

    def test_equal_score_candidates_beyond_first_twenty_remain_reachable(self):
        recipes = [self.recipe(n) for n in range(1, 31)]
        tail = {recipe["recipe_id"] for recipe in recipes[20:]}
        selected = {self.run_recommend(recipes, mode="development", seed=s)["selected"]["recipe_id"]
                    for s in range(64)}
        self.assertTrue(selected & tail, "Equally eligible recipes after index 20 were permanently cut off")

    def test_recommendation_does_not_mutate_request_or_input_recipe(self):
        recipe = self.recipe()
        request = self.request(constraints={"pantry_mode": "only_owned", "owned_ingredients": ["ing_tomato"]})
        before = deepcopy((recipe, request))
        self.run_recommend([recipe], request)
        self.assertEqual((recipe, request), before)


if __name__ == "__main__":
    unittest.main()
