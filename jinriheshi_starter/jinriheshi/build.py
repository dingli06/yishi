from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from . import ADAPTER_VERSION, SCHEMA_VERSION
from .adapters.howtocook import HowToCookAdapter
from .common import atomic_write, canonical_bytes, digest, read_json, safe_local_path, write_json


def build(root: Path) -> dict[str, Any]:
    lock = read_json(root / "data/sources/howtocook.lock.json")
    overlays = read_json(root / "data/overlays/howtocook_seed.json")
    if overlays["source_revision"] != lock["revision"]:
        raise ValueError("Overlay revision is stale; rebase annotations explicitly before updating the dataset")
    annotations = {r["source_path"]: r for r in overlays["recipes"]}
    if len(annotations) != len(overlays["recipes"]):
        raise ValueError("Duplicate source_path in seed overlays")
    identity = read_json(root / "data/identity/overrides.json")
    adapter = HowToCookAdapter()
    recipes = []
    source_files = [f for f in lock["files"] if f.get("kind") == "recipe"]
    for source in sorted(source_files, key=lambda x: x["source_path"]):
        raw = safe_local_path(root, source["local_path"]).read_bytes()
        if digest(raw) != source["content_sha256"]:
            raise ValueError(f"SHA256 mismatch: {source['source_path']}")
        git_hash = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if git_hash != source["blob_sha"]:
            raise ValueError(f"Git blob hash mismatch: {source['source_path']}")
        context = {**source, "revision": lock["revision"]}
        recipes.append(adapter.normalize(raw=raw, source=context,
                                         overlay=annotations.get(source["source_path"]), identity=identity))
    unlinked = sorted(set(annotations) - {r["source"]["source_path"] for r in recipes})
    if unlinked:
        raise ValueError(f"Overlays without matching source files: {unlinked}")
    # Validate the full batch before replacing any generated data file.
    from .validate import validate_records
    errors = validate_records(root, recipes)
    if errors:
        raise ValueError("Build rejected:\n" + "\n".join(errors[:30]))
    seeds = [r for r in recipes if r["publication"]["state"] == "development"]
    full_bytes = b"".join(canonical_bytes(r) for r in recipes)
    seed_bytes = b"".join(canonical_bytes(r) for r in seeds)
    catalog = [{"recipe_id": r["recipe_id"], "dish_id": r["dish_id"],
                "recipe_version": r["recipe_version"], "title": r["title"],
                "source_category": r["source_category"], "state": r["publication"]["state"],
                "source_path": r["source"]["source_path"]} for r in recipes]
    report = {"schema_version": SCHEMA_VERSION, "adapter_version": ADAPTER_VERSION,
              "source_revision": lock["revision"], "recipe_count": len(recipes),
              "seed_count": len(seeds), "published_count": 0,
              "states": dict(sorted(Counter(r["publication"]["state"] for r in recipes).items())),
              "categories": dict(sorted(Counter(r["source_category"] for r in recipes).items())),
              "seed_review_states": dict(sorted(Counter(r["review"]["status"] for r in seeds).items())),
              "audited_total_time_count": sum(r["time"]["status"] == "verified" for r in seeds),
              "image_files_included": 0,
              "files": {"recipes.jsonl": digest(full_bytes), "seed_recipes.jsonl": digest(seed_bytes)},
              "notes": ["开发样板由代理依据原文整理；未经人审和实烹，不是生产发布库。",
                        "372是文档记录数，含饮料、调料、甜品及半成品，不是完整餐食数。",
                        "构建结果不包含抓取时间，输入相同则字节相同。"]}
    target = root / "data/generated"
    atomic_write(target / "recipes.jsonl", full_bytes)
    atomic_write(target / "seed_recipes.jsonl", seed_bytes)
    write_json(target / "catalog.json", catalog)
    # Commit marker written last; readers verify checksums to detect an interrupted build.
    write_json(target / "build_report.json", report)
    return report
