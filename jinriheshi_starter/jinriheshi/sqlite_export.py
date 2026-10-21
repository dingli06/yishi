from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from .common import canonical_bytes
from .storage import JsonRecipeRepository


def export_sqlite(root: Path, output: Path) -> dict[str, Any]:
    """可重建的开发镜像，不在这里存用户数据或覆盖业务数据库。"""
    if output.suffix.lower() not in {".sqlite", ".db"}:
        raise ValueError("SQLite export requires a .sqlite or .db output path")
    if output.exists():
        try:
            with closing(sqlite3.connect(f"file:{output.resolve().as_posix()}?mode=ro", uri=True)) as existing:
                row = existing.execute("SELECT value FROM dataset_meta WHERE key='managed_by'").fetchone()
            if row != ("jinriheshi-data-starter",):
                raise ValueError("Refusing to replace an unmanaged database")
        except sqlite3.DatabaseError as exc:
            raise ValueError("Refusing to replace an unrelated file or database") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="recipes-", suffix=".sqlite.tmp", dir=output.parent)
    os.close(fd)
    records = list(JsonRecipeRepository(root / "data/generated/recipes.jsonl").all())
    try:
        with closing(sqlite3.connect(temporary)) as conn, conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript((root / "contracts/sqlite_schema.sql").read_text(encoding="utf-8"))
            for recipe in records:
                conn.execute("INSERT OR IGNORE INTO dishes(dish_id, display_name) VALUES (?,?)",
                             (recipe["dish_id"], recipe["title"]))
                conn.execute("INSERT INTO recipe_versions VALUES (?,?,?,?,?,?,?,?,?)",
                             (recipe["recipe_id"], recipe["recipe_version"], recipe["dish_id"],
                              recipe["title"], recipe["source"]["source_id"], recipe["source"]["source_path"],
                              recipe["source"]["revision"], recipe["publication"]["state"],
                              canonical_bytes(recipe).decode("utf-8")))
            conn.execute("INSERT INTO dataset_meta VALUES (?,?)", ("schema_version", "1.0.0"))
            conn.execute("INSERT INTO dataset_meta VALUES (?,?)", ("managed_by", "jinriheshi-data-starter"))
            count = conn.execute("SELECT COUNT(*) FROM recipe_versions").fetchone()[0]
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"recipe_count": count, "output": str(output)}
