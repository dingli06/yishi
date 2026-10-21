from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from jsonschema import Draft202012Validator

from .common import read_json
from .recommend import recommend
from .storage import RecipeRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class ApplicationError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


APPLICATION_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS subjects (
  subject_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  constraints_json TEXT NOT NULL CHECK(json_valid(constraints_json)),
  preferences_json TEXT NOT NULL CHECK(json_valid(preferences_json)),
  revision INTEGER NOT NULL CHECK(revision >= 1),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_subject ON sessions(subject_id);
CREATE TABLE IF NOT EXISTS recommendations (
  recommendation_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  session_revision INTEGER NOT NULL,
  recipe_id TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  dish_id TEXT NOT NULL,
  result_json TEXT NOT NULL CHECK(json_valid(result_json)),
  allocated_at TEXT NOT NULL,
  UNIQUE(session_id, session_revision)
);
CREATE INDEX IF NOT EXISTS idx_recommendations_session ON recommendations(session_id);
CREATE TABLE IF NOT EXISTS idempotency (
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  route TEXT NOT NULL,
  key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL CHECK(json_valid(response_json)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(subject_id, route, key)
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  recommendation_id TEXT NOT NULL REFERENCES recommendations(recommendation_id),
  recipe_id TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
  occurred_at TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_subject_type ON events(subject_id, event_type);
CREATE TABLE IF NOT EXISTS favorites (
  subject_id TEXT NOT NULL REFERENCES subjects(subject_id),
  recipe_id TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  dish_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(subject_id, recipe_id, recipe_version)
);
CREATE TABLE IF NOT EXISTS subject_settings (
  subject_id TEXT PRIMARY KEY REFERENCES subjects(subject_id),
  permanent_excluded_ingredient_ids TEXT NOT NULL CHECK(json_valid(permanent_excluded_ingredient_ids)),
  updated_at TEXT NOT NULL
);
PRAGMA user_version = 1;
"""


class ApplicationRepository:
    """Stores user application state separately from the rebuildable recipe mirror."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(APPLICATION_SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()


class ApplicationService:
    def __init__(self, application_repository: ApplicationRepository,
                 recipe_repository: RecipeRepository, project_root: Path, *,
                 mode: str = "production", development_seed: int | None = None,
                 id_factory: Callable[[], str] | None = None):
        if mode not in {"production", "development"}:
            raise ValueError("Unsupported mode")
        if mode == "production" and development_seed is not None:
            raise ValueError("A fixed seed is not allowed in production")
        self.application_repository = application_repository
        self.recipe_repository = recipe_repository
        self.mode = mode
        self.development_seed = development_seed
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)
        schema_dir = project_root / "schemas"
        self.request_validator = Draft202012Validator(read_json(schema_dir / "recommendation_request.schema.json"))
        self.event_validator = Draft202012Validator(read_json(schema_dir / "event.schema.json"))
        ingredients = read_json(project_root / "data" / "dictionaries" / "ingredients.json")["items"]
        equipment = read_json(project_root / "data" / "dictionaries" / "equipment.json")["items"]
        tags = read_json(project_root / "data" / "dictionaries" / "tags.json")["items"]
        self.ingredient_dictionary = {item["id"]: item for item in ingredients}
        self.equipment_ids = {item["id"] for item in equipment}
        self.tag_ids = {item["id"] for item in tags}

    @staticmethod
    def _require_key(key: str) -> None:
        if not 16 <= len(key) <= 128:
            raise ApplicationError("validation_error", "Idempotency-Key must be 16 to 128 characters", status=422)

    @staticmethod
    def _subject(connection: sqlite3.Connection, subject_id: str) -> None:
        if not subject_id:
            raise ApplicationError("unauthorized", "A trusted subject is required", status=401)
        connection.execute("INSERT OR IGNORE INTO subjects(subject_id, created_at) VALUES (?, ?)",
                           (subject_id, _now()))

    @staticmethod
    def _idempotent_response(connection: sqlite3.Connection, subject_id: str, route: str,
                             key: str, request_hash: str) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT request_hash, response_json FROM idempotency WHERE subject_id=? AND route=? AND key=?",
            (subject_id, route, key),
        ).fetchone()
        if not row:
            return None
        if row["request_hash"] != request_hash:
            raise ApplicationError("idempotency_conflict", "The key was already used for a different request", status=409)
        return json.loads(row["response_json"])

    @staticmethod
    def _save_idempotent(connection: sqlite3.Connection, subject_id: str, route: str,
                         key: str, request_hash: str, response: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO idempotency(subject_id, route, key, request_hash, response_json, created_at) VALUES (?,?,?,?,?,?)",
            (subject_id, route, key, request_hash, _canonical(response), _now()),
        )

    def _validate_request(self, constraints: dict[str, Any], preferences: dict[str, Any]) -> None:
        value = {"schema_version": "1.0.0", "constraints": constraints, "preferences": preferences}
        errors = sorted(self.request_validator.iter_errors(value), key=lambda item: list(item.path))
        if errors:
            raise ApplicationError("validation_error", errors[0].message, status=422)
        required = set(constraints.get("required_ingredients", []))
        excluded = set(constraints.get("excluded_ingredients", []))
        if required & excluded:
            raise ApplicationError("constraint_conflict", "The same ingredient cannot be required and excluded", status=422)
        if constraints.get("pantry_mode") == "allow_missing" and constraints.get("max_missing_ingredients") is None:
            raise ApplicationError("validation_error", "allow_missing requires max_missing_ingredients", status=422)
        ingredient_values = set(constraints.get("owned_ingredients", [])) | required | excluded | set(
            preferences.get("priority_ingredients", []))
        unknown = ingredient_values - set(self.ingredient_dictionary)
        if unknown:
            raise ApplicationError("unknown_option", f"Unknown ingredient: {sorted(unknown)[0]}", status=422)
        unknown_equipment = set(constraints.get("available_equipment") or []) - self.equipment_ids
        if unknown_equipment:
            raise ApplicationError("unknown_option", f"Unknown equipment: {sorted(unknown_equipment)[0]}", status=422)
        tag_values = set(constraints.get("cuisines_only", []))
        for field in ("tastes", "cuisines", "textures"):
            tag_values.update(preferences.get(field, []))
        unknown_tags = tag_values - self.tag_ids
        if unknown_tags:
            raise ApplicationError("unknown_option", f"Unknown tag: {sorted(unknown_tags)[0]}", status=422)

    def create_session(self, subject_id: str, constraints: dict[str, Any], preferences: dict[str, Any],
                       idempotency_key: str) -> dict[str, Any]:
        self._require_key(idempotency_key)
        self._validate_request(constraints, preferences)
        request_hash = _hash({"constraints": constraints, "preferences": preferences})
        with self.application_repository.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._subject(connection, subject_id)
                replay = self._idempotent_response(connection, subject_id, "POST /v1/sessions",
                                                    idempotency_key, request_hash)
                if replay is not None:
                    connection.commit()
                    return replay
                session_id = "ses_" + self.id_factory()
                response = {"session_id": session_id, "revision": 1}
                connection.execute(
                    "INSERT INTO sessions(session_id, subject_id, constraints_json, preferences_json, revision, created_at) VALUES (?,?,?,?,?,?)",
                    (session_id, subject_id, _canonical(constraints), _canonical(preferences), 1, _now()),
                )
                self._save_idempotent(connection, subject_id, "POST /v1/sessions", idempotency_key,
                                      request_hash, response)
                connection.commit()
                return response
            except Exception:
                connection.rollback()
                raise

    def _context(self, connection: sqlite3.Connection, subject_id: str, session_id: str) -> dict[str, Any]:
        seen = [row["dish_id"] for row in connection.execute(
            "SELECT dish_id FROM recommendations WHERE session_id=?", (session_id,)).fetchall()]
        favorites = [row["dish_id"] for row in connection.execute(
            "SELECT dish_id FROM favorites WHERE subject_id=?", (subject_id,)).fetchall()]
        cooked = [row["dish_id"] for row in connection.execute(
            "SELECT DISTINCT r.dish_id FROM events e JOIN recommendations r ON r.recommendation_id=e.recommendation_id "
            "WHERE e.subject_id=? AND (e.event_type='cooked' OR "
            "(e.event_type='reject' AND json_extract(e.payload_json, '$.reason')='recently_ate'))",
            (subject_id,)).fetchall()]
        return {"seen_dish_ids": seen, "favorite_dish_ids": favorites,
                "recently_cooked_dish_ids": cooked}

    def next_recommendation(self, subject_id: str, session_id: str, expected_revision: int,
                            idempotency_key: str) -> dict[str, Any]:
        self._require_key(idempotency_key)
        route = f"POST /v1/sessions/{session_id}/recommendations"
        request_hash = _hash({"expected_revision": expected_revision})
        with self.application_repository.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._subject(connection, subject_id)
                replay = self._idempotent_response(connection, subject_id, route, idempotency_key, request_hash)
                if replay is not None:
                    connection.commit()
                    return replay
                session = connection.execute(
                    "SELECT * FROM sessions WHERE session_id=? AND subject_id=?", (session_id, subject_id)).fetchone()
                if not session:
                    raise ApplicationError("session_not_found", "Session not found", status=404)
                if session["revision"] != expected_revision:
                    raise ApplicationError("session_revision_conflict", "Session revision changed", status=409)
                constraints = json.loads(session["constraints_json"])
                settings = connection.execute(
                    "SELECT permanent_excluded_ingredient_ids FROM subject_settings WHERE subject_id=?", (subject_id,)).fetchone()
                if settings:
                    constraints["excluded_ingredients"] = sorted(set(constraints.get("excluded_ingredients", [])) |
                                                                set(json.loads(settings[0])))
                request = {"schema_version": "1.0.0", "constraints": constraints,
                           "preferences": json.loads(session["preferences_json"]),
                           "context": self._context(connection, subject_id, session_id)}
                domain = recommend(self.recipe_repository.all(), request, self.ingredient_dictionary,
                                   mode=self.mode, seed=self.development_seed)
                recommendation_id = None
                new_revision = session["revision"]
                if domain["selected"]:
                    recommendation_id = "rec_" + self.id_factory()
                    new_revision += 1
                    selected = domain["selected"]
                    connection.execute(
                        "INSERT INTO recommendations(recommendation_id, session_id, session_revision, recipe_id, recipe_version, dish_id, result_json, allocated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (recommendation_id, session_id, new_revision, selected["recipe_id"],
                         selected["recipe_version"], selected["dish_id"], _canonical(domain), _now()),
                    )
                    connection.execute("UPDATE sessions SET revision=? WHERE session_id=?", (new_revision, session_id))
                response = {"recommendation_id": recommendation_id, "session_revision": new_revision,
                            "result": domain}
                self._save_idempotent(connection, subject_id, route, idempotency_key, request_hash, response)
                connection.commit()
                return response
            except Exception:
                connection.rollback()
                raise

    def apply_event(self, subject_id: str, event: dict[str, Any]) -> dict[str, Any]:
        errors = sorted(self.event_validator.iter_errors(event), key=lambda item: list(item.path))
        if errors:
            raise ApplicationError("validation_error", errors[0].message, status=422)
        valid_scope = {
            "shown": {"session"}, "skip": {"session"}, "accept": {"session"},
            "favorite": {"session"}, "unfavorite": {"session"}, "cooked": {"recent"},
            "reject": {"session", "recent", "permanent"},
        }
        if event["scope"] not in valid_scope[event["type"]]:
            raise ApplicationError("validation_error", "Illegal event type/scope combination", status=422)
        unknown_targets = set(event["permanent_excluded_ingredient_ids"]) - set(self.ingredient_dictionary)
        if unknown_targets:
            raise ApplicationError("unknown_option", f"Unknown ingredient: {sorted(unknown_targets)[0]}", status=422)
        payload_hash = _hash(event)
        with self.application_repository.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._subject(connection, subject_id)
                existing = connection.execute("SELECT payload_hash FROM events WHERE event_id=?", (event["event_id"],)).fetchone()
                if existing:
                    if existing["payload_hash"] != payload_hash:
                        raise ApplicationError("idempotency_conflict", "The event ID has different content", status=409)
                    connection.commit()
                    return {"event_id": event["event_id"], "applied": True}
                recommendation = connection.execute(
                    "SELECT r.*, s.subject_id FROM recommendations r JOIN sessions s ON s.session_id=r.session_id "
                    "WHERE r.recommendation_id=? AND r.session_id=? AND s.subject_id=?",
                    (event["recommendation_id"], event["session_id"], subject_id),
                ).fetchone()
                if not recommendation:
                    raise ApplicationError("session_not_found", "Recommendation not found", status=404)
                if (recommendation["recipe_id"], recommendation["recipe_version"]) != (
                        event["recipe_id"], event["recipe_version"]):
                    raise ApplicationError("validation_error", "Event does not match the allocated recipe version", status=422)
                connection.execute(
                    "INSERT INTO events(event_id, subject_id, session_id, recommendation_id, recipe_id, recipe_version, event_type, payload_hash, payload_json, occurred_at, received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (event["event_id"], subject_id, event["session_id"], event["recommendation_id"],
                     event["recipe_id"], event["recipe_version"], event["type"], payload_hash,
                     _canonical(event), event["occurred_at"], _now()),
                )
                if event["type"] == "favorite":
                    connection.execute(
                        "INSERT OR IGNORE INTO favorites(subject_id, recipe_id, recipe_version, dish_id, created_at) VALUES (?,?,?,?,?)",
                        (subject_id, event["recipe_id"], event["recipe_version"], recommendation["dish_id"], _now()),
                    )
                elif event["type"] == "unfavorite":
                    connection.execute("DELETE FROM favorites WHERE subject_id=? AND recipe_id=? AND recipe_version=?",
                                       (subject_id, event["recipe_id"], event["recipe_version"]))
                if event["scope"] == "permanent":
                    current = connection.execute(
                        "SELECT permanent_excluded_ingredient_ids FROM subject_settings WHERE subject_id=?", (subject_id,)).fetchone()
                    values = set(json.loads(current[0])) if current else set()
                    values.update(event["permanent_excluded_ingredient_ids"])
                    connection.execute(
                        "INSERT INTO subject_settings(subject_id, permanent_excluded_ingredient_ids, updated_at) VALUES (?,?,?) "
                        "ON CONFLICT(subject_id) DO UPDATE SET permanent_excluded_ingredient_ids=excluded.permanent_excluded_ingredient_ids, updated_at=excluded.updated_at",
                        (subject_id, _canonical(sorted(values)), _now()),
                    )
                connection.commit()
                return {"event_id": event["event_id"], "applied": True}
            except Exception:
                connection.rollback()
                raise

    def list_favorites(self, subject_id: str) -> list[dict[str, Any]]:
        with self.application_repository.connect() as connection:
            rows = connection.execute(
                "SELECT recipe_id, recipe_version, dish_id, created_at FROM favorites WHERE subject_id=? ORDER BY created_at DESC",
                (subject_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_settings(self, subject_id: str) -> dict[str, Any]:
        with self.application_repository.connect() as connection:
            row = connection.execute(
                "SELECT permanent_excluded_ingredient_ids FROM subject_settings WHERE subject_id=?", (subject_id,)).fetchone()
        return {"permanent_excluded_ingredient_ids": json.loads(row[0]) if row else []}
