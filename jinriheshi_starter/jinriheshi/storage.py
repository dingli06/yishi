from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Protocol

from .common import digest, read_json


class RecipeRepository(Protocol):
    def all(self) -> Iterable[dict[str, Any]]: ...
    def get(self, recipe_id: str, recipe_version: str | None = None) -> dict[str, Any] | None: ...


class JsonRecipeRepository:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        marker = path.parent / "build_report.json"
        if not marker.exists():
            raise ValueError("Missing build marker; run build before reading generated data")
        expected = read_json(marker).get("files", {}).get(path.name)
        if not expected or digest(raw) != expected:
            raise ValueError("Generated data does not match build marker; rerun build")
        self.records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]

    def all(self) -> Iterable[dict[str, Any]]:
        return iter(self.records)

    def get(self, recipe_id: str, recipe_version: str | None = None) -> dict[str, Any] | None:
        return next((r for r in self.records if r["recipe_id"] == recipe_id and
                     (recipe_version is None or r["recipe_version"] == recipe_version)), None)


class SqliteRecipeRepository:
    def __init__(self, path: Path):
        self.path = path

    def all(self) -> Iterable[dict[str, Any]]:
        with closing(sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)) as connection:
            rows = connection.execute("SELECT payload FROM recipe_versions ORDER BY source_path").fetchall()
        return (json.loads(row[0]) for row in rows)

    def get(self, recipe_id: str, recipe_version: str | None = None) -> dict[str, Any] | None:
        query = "SELECT payload FROM recipe_versions WHERE recipe_id = ?"
        values: list[Any] = [recipe_id]
        if recipe_version is not None:
            query += " AND recipe_version = ?"
            values.append(recipe_version)
        with closing(sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)) as connection:
            row = connection.execute(query, values).fetchone()
        return json.loads(row[0]) if row else None
