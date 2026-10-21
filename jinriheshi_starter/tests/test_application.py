from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jinriheshi.application import ApplicationError, ApplicationRepository, ApplicationService
from jinriheshi.storage import JsonRecipeRepository


ROOT = Path(__file__).resolve().parents[1]


class ApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        app_repository = ApplicationRepository(Path(self.temp.name) / "application.sqlite")
        recipes = JsonRecipeRepository(ROOT / "data" / "generated" / "seed_recipes.jsonl")
        self.service = ApplicationService(app_repository, recipes, ROOT, mode="development", development_seed=42)
        self.subject = "subject-alice"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_session(self, *, key: str = "create-session-key-0001",
                       constraints: dict | None = None, preferences: dict | None = None):
        return self.service.create_session(self.subject, constraints or {}, preferences or {}, key)

    def next(self, session: dict, *, key: str = "next-recipe-key-00001"):
        return self.service.next_recommendation(
            self.subject, session["session_id"], session["revision"], key)

    @staticmethod
    def event_for(response: dict, session_id: str, event_type: str, *,
                  event_id: str = "event-identifier-0001", scope: str = "session",
                  reason=None, confirmed=False, excluded=None):
        selected = response["result"]["selected"]
        return {
            "schema_version": "1.0.0",
            "event_id": event_id,
            "session_id": session_id,
            "recommendation_id": response["recommendation_id"],
            "recipe_id": selected["recipe_id"],
            "recipe_version": selected["recipe_version"],
            "type": event_type,
            "reason": reason,
            "occurred_at": "2026-10-21T12:00:00Z",
            "scope": scope,
            "confirmed_permanent": confirmed,
            "permanent_excluded_ingredient_ids": excluded or [],
        }

    def test_create_session_idempotency_and_conflict(self):
        first = self.create_session()
        replay = self.create_session()
        self.assertEqual(first, replay)
        with self.assertRaisesRegex(ApplicationError, "different request") as caught:
            self.create_session(preferences={"novelty": "new"})
        self.assertEqual(caught.exception.code, "idempotency_conflict")

    def test_session_rejects_unknown_ids_and_conflicting_constraints(self):
        with self.assertRaises(ApplicationError) as unknown:
            self.create_session(constraints={"required_ingredients": ["ing_does_not_exist"]})
        self.assertEqual(unknown.exception.code, "unknown_option")
        with self.assertRaises(ApplicationError) as conflict:
            self.create_session(key="create-session-key-0002", constraints={
                "required_ingredients": ["ing_egg"], "excluded_ingredients": ["ing_egg"]})
        self.assertEqual(conflict.exception.code, "constraint_conflict")

    def test_recommendation_replay_revision_and_dish_deduplication(self):
        session = self.create_session()
        first = self.next(session)
        self.assertIsNotNone(first["recommendation_id"])
        self.assertEqual(first["session_revision"], 2)
        replay = self.next(session)
        self.assertEqual(first, replay)
        with self.assertRaises(ApplicationError) as stale:
            self.service.next_recommendation(
                self.subject, session["session_id"], 1, "next-recipe-key-00002")
        self.assertEqual(stale.exception.code, "session_revision_conflict")
        second = self.service.next_recommendation(
            self.subject, session["session_id"], 2, "next-recipe-key-00003")
        self.assertNotEqual(first["result"]["selected"]["dish_id"],
                            second["result"]["selected"]["dish_id"])

    def test_concurrent_next_request_has_one_winner(self):
        session = self.create_session()

        def invoke(key: str):
            try:
                return self.service.next_recommendation(self.subject, session["session_id"], 1, key)
            except ApplicationError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(invoke, ["concurrent-next-key-001", "concurrent-next-key-002"]))
        successes = [item for item in results if isinstance(item, dict)]
        failures = [item for item in results if isinstance(item, str)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(failures, ["session_revision_conflict"])

    def test_cross_subject_cannot_read_session(self):
        session = self.create_session()
        with self.assertRaises(ApplicationError) as missing:
            self.service.next_recommendation(
                "subject-bob", session["session_id"], 1, "bob-next-key-000001")
        self.assertEqual(missing.exception.code, "session_not_found")

    def test_favorite_event_is_idempotent_and_accept_is_not_cooked(self):
        session = self.create_session()
        result = self.next(session)
        event = self.event_for(result, session["session_id"], "favorite")
        first = self.service.apply_event(self.subject, event)
        self.assertEqual(first, self.service.apply_event(self.subject, event))
        self.assertEqual(len(self.service.list_favorites(self.subject)), 1)

        changed = dict(event, type="accept")
        with self.assertRaises(ApplicationError) as conflict:
            self.service.apply_event(self.subject, changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")

        accept = self.event_for(result, session["session_id"], "accept",
                                event_id="event-identifier-0002")
        self.service.apply_event(self.subject, accept)
        with self.service.application_repository.connect() as connection:
            cooked = connection.execute(
                "SELECT count(*) FROM events WHERE subject_id=? AND event_type='cooked'", (self.subject,)).fetchone()[0]
        self.assertEqual(cooked, 0)

    def test_event_must_match_allocated_version_and_owner(self):
        session = self.create_session()
        result = self.next(session)
        wrong = self.event_for(result, session["session_id"], "accept")
        wrong["recipe_version"] = "rv_wrong"
        with self.assertRaises(ApplicationError) as mismatch:
            self.service.apply_event(self.subject, wrong)
        self.assertEqual(mismatch.exception.code, "validation_error")
        valid = self.event_for(result, session["session_id"], "accept",
                               event_id="event-identifier-0003")
        with self.assertRaises(ApplicationError) as other:
            self.service.apply_event("subject-bob", valid)
        self.assertEqual(other.exception.code, "session_not_found")

    def test_permanent_rejection_has_explicit_target_and_updates_settings(self):
        session = self.create_session()
        result = self.next(session)
        selected_ids = result["result"]["selected"]["selected_ingredient_ids"]
        target = selected_ids[0]
        event = self.event_for(
            result, session["session_id"], "reject",
            event_id="event-identifier-0004", scope="permanent", reason="always_dislike",
            confirmed=True, excluded=[target],
        )
        self.service.apply_event(self.subject, event)
        self.assertEqual(self.service.get_settings(self.subject),
                         {"permanent_excluded_ingredient_ids": [target]})

        unknown = dict(event, event_id="event-identifier-0005",
                       permanent_excluded_ingredient_ids=["ing_not_real"])
        with self.assertRaises(ApplicationError) as invalid:
            self.service.apply_event(self.subject, unknown)
        self.assertEqual(invalid.exception.code, "unknown_option")

    def test_only_recently_ate_rejection_enters_recent_context(self):
        session = self.create_session()
        result = self.next(session)
        not_today = self.event_for(
            result, session["session_id"], "reject", event_id="event-identifier-0006",
            scope="session", reason="not_today")
        self.service.apply_event(self.subject, not_today)
        with self.service.application_repository.connect() as connection:
            context = self.service._context(connection, self.subject, session["session_id"])
        self.assertNotIn(result["result"]["selected"]["dish_id"], context["recently_cooked_dish_ids"])

        recently = self.event_for(
            result, session["session_id"], "reject", event_id="event-identifier-0007",
            scope="recent", reason="recently_ate")
        self.service.apply_event(self.subject, recently)
        with self.service.application_repository.connect() as connection:
            context = self.service._context(connection, self.subject, session["session_id"])
        self.assertIn(result["result"]["selected"]["dish_id"], context["recently_cooked_dish_ids"])

    def test_production_mode_cannot_serve_development_seed_data(self):
        repository = ApplicationRepository(Path(self.temp.name) / "production.sqlite")
        recipes = JsonRecipeRepository(ROOT / "data" / "generated" / "seed_recipes.jsonl")
        service = ApplicationService(repository, recipes, ROOT, mode="production")
        session = service.create_session(self.subject, {}, {}, "production-create-0001")
        response = service.next_recommendation(
            self.subject, session["session_id"], 1, "production-next-key-01")
        self.assertEqual(response["result"]["status"], "no_candidate")
        self.assertIsNone(response["recommendation_id"])
        self.assertEqual(response["session_revision"], 1)


if __name__ == "__main__":
    unittest.main()
