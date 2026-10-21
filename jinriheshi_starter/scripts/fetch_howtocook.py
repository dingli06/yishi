#!/usr/bin/env python3
"""Fetch a pinned, text-only HowToCook snapshot and verify every Git blob.

Uses only the Python standard library. Run --offline for a network-free audit.
No branch names are accepted: changing a source requires an explicit 40-hex
--revision. Old snapshot directories remain immutable and available for audit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
from urllib.parse import quote, urlparse, unquote
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener

DEFAULT_REVISION = "0e106eea348c734fe1586f781202994439cf98a5"
REPOSITORY = "Anduin2017/HowToCook"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = Path("data/sources/howtocook.lock.json")
TREE_PATH = Path("data/sources/upstream-tree.json")
SEED_NAMES = {
    "西红柿炒鸡蛋", "凉拌黄瓜", "酸辣土豆丝", "手撕包菜", "蒜蓉西兰花",
    "清蒸南瓜", "皮蛋豆腐", "炒青菜", "麻婆豆腐", "可乐鸡翅", "红烧鸡翅",
    "香菇滑鸡", "回锅肉", "糖醋排骨", "白灼虾", "清蒸鲈鱼", "红烧鱼",
    "蛋炒饭", "葱油拌面", "日式肥牛丼饭", "西红柿鸡蛋挂面", "电饭煲蒸米饭",
    "银耳莲子粥", "紫菜蛋花汤", "番茄牛肉蛋花汤", "金针菇汤", "茶叶蛋",
    "太阳蛋", "微波炉鸡蛋羹", "卤菜",
}


def revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("revision must be a lowercase, full 40-character Git SHA")
    return value


def source_path(value: str) -> str:
    """Only the explicitly supported upstream text paths may enter the bundle."""
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise ValueError("unsafe source path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("non-canonical source path")
    if value in {"LICENSE", "README.md"}:
        return value
    if not value.startswith("dishes/") or not value.endswith(".md"):
        raise ValueError("only recipe Markdown, LICENSE and README.md are allowed")
    if value.startswith("dishes/template/"):
        raise ValueError("template is not a recipe")
    return value


def blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def allowed_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme != "https" or p.username or p.password or p.port or p.fragment:
        return False
    if p.hostname == "raw.githubusercontent.com" and not p.query:
        prefix = f"/{REPOSITORY}/"
        if not p.path.startswith(prefix):
            return False
        parts = p.path[len(prefix):].split("/", 1)
        try:
            if len(parts) != 2:
                return False
            revision(parts[0]); source_path(unquote(parts[1]))
            return True
        except ValueError:
            return False
    return bool(p.hostname == "api.github.com" and p.query in {"", "recursive=1"}
                and re.fullmatch(f"/repos/{REPOSITORY}/git/trees/[0-9a-f]{{40}}", p.path))


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError("redirect outside the allowed public source")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_url(url: str) -> bytes:
    if not allowed_url(url):
        raise ValueError("URL outside the allowed public source")
    last_error = None
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "jinriheshi-source-import/0.1"})
            with build_opener(SafeRedirect()).open(request, timeout=30) as response:
                content = response.read(8 * 1024 * 1024 + 1)
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError("upstream text response exceeds 8 MiB")
                return content
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"could not read public source: {url}") from last_error


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def safe_local(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("local path escapes project root (possibly through a symlink)")
    return path


def select_files(tree: dict) -> list[dict]:
    if tree.get("truncated"):
        raise ValueError("upstream Git tree is truncated")
    result = []
    seen = set()
    for entry in tree.get("tree", []):
        name = entry.get("path", "")
        if name.startswith("dishes/template/"):
            continue
        if name in {"LICENSE", "README.md"} or (name.startswith("dishes/") and name.endswith(".md")):
            source_path(name)
            if entry.get("type") != "blob" or entry.get("mode") == "120000":
                raise ValueError(f"source is not an ordinary Git blob: {name}")
            if name in seen:
                raise ValueError(f"duplicate path in tree: {name}")
            seen.add(name)
            result.append({"path": name, "sha": revision(entry.get("sha", ""))})
    if not {"LICENSE", "README.md"}.issubset(seen):
        raise ValueError("tree must contain upstream LICENSE and README.md")
    if not any(x["path"].startswith("dishes/") for x in result):
        raise ValueError("tree has no recipes")
    return sorted(result, key=lambda item: item["path"])


def ensure_file(root: Path, rev: str, entry: dict, cache: Path | None, offline: bool) -> dict:
    name = source_path(entry["path"])
    local_relative = f"data/raw/howtocook/{rev}/{name}"
    destination = safe_local(root, local_relative)
    source_url = f"https://raw.githubusercontent.com/{REPOSITORY}/{rev}/{quote(name, safe='/')}"
    content = None
    if destination.exists():
        content = destination.read_bytes()
        if blob_sha(content) != entry["sha"]:
            # Never silently overwrite an existing, modified immutable source.
            raise ValueError(f"existing source differs from locked blob: {name}")
    if content is None and cache:
        candidate = safe_local(cache, name)
        if candidate.exists():
            cached = candidate.read_bytes()
            if blob_sha(cached) == entry["sha"]:
                content = cached
    if content is None:
        if offline:
            raise FileNotFoundError(f"offline source missing: {name}")
        content = read_url(source_url)
    if blob_sha(content) != entry["sha"]:
        raise ValueError(f"downloaded Git blob checksum mismatch: {name}")
    content.decode("utf-8")
    if not destination.exists():
        atomic_write(destination, content)
    return {
        "source_path": name,
        "blob_sha": entry["sha"],
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "local_path": local_relative,
        "source_url": source_url,
        "size_bytes": len(content),
        "kind": "recipe" if name.startswith("dishes/") else ("license" if name == "LICENSE" else "readme"),
    }


def synchronize(root: Path, rev: str, tree: dict, *, cache: Path | None = None,
                offline: bool = False, workers: int = 8) -> dict:
    revision(rev)
    entries = select_files(tree)
    # Seed records are acquired first; a partial acquisition does not publish a lock.
    priority = [x for x in entries if PurePosixPath(x["path"]).stem in SEED_NAMES]
    remaining = [x for x in entries if x not in priority]
    records = []
    for phase, group in [("seed", priority), ("remaining", remaining)]:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
            jobs = {executor.submit(ensure_file, root, rev, x, cache, offline): x for x in group}
            errors = []
            for job in as_completed(jobs):
                try:
                    records.append(job.result())
                except Exception as exc:
                    errors.append(f"{jobs[job]['path']}: {exc}")
            if errors:
                raise RuntimeError("snapshot acquisition failed; lock was not changed:\n" + "\n".join(errors))
        print(f"{phase}: verified {len(group)} files", flush=True)
    records.sort(key=lambda item: item["source_path"])
    manifest = {
        "schema_version": "1.0.0",
        "manifest_version": "1.0.0",
        "source_id": "howtocook",
        "repository": f"https://github.com/{REPOSITORY}",
        "revision": rev,
        "upstream_tree_sha": tree.get("sha"),
        "license_spdx": "Unlicense",
        "license": "Unlicense",
        "content_scope": "recipe_markdown_only_no_images_or_videos",
        "recipe_count": sum(x["kind"] == "recipe" for x in records),
        "file_count": len(records),
        "files": records,
    }
    # The manifest is the commit marker: it is only replaced after every file passes.
    atomic_write(safe_local(root, TREE_PATH.as_posix()), json_bytes(tree))
    atomic_write(safe_local(root, LOCK_PATH.as_posix()), json_bytes(manifest))
    return manifest


def verify_manifest(root: Path) -> dict:
    """Validate the committed lock, tree and local bytes without writing anything."""
    lock = json.loads(safe_local(root, LOCK_PATH.as_posix()).read_text(encoding="utf-8"))
    tree = json.loads(safe_local(root, TREE_PATH.as_posix()).read_text(encoding="utf-8"))
    rev = revision(lock["revision"])
    entries = {x["path"]: x for x in select_files(tree)}
    records = lock["files"]
    if len(records) != len(entries) or {x["source_path"] for x in records} != set(entries):
        raise ValueError("manifest paths do not match the complete upstream text tree")
    if lock.get("upstream_tree_sha") != tree.get("sha"):
        raise ValueError("manifest/tree revision mismatch")
    for record in records:
        expected = ensure_file(root, rev, entries[record["source_path"]], None, True)
        # ensure_file above is read-only because existence was checked here.
        for key, value in expected.items():
            if record.get(key) != value:
                raise ValueError(f"manifest mismatch: {record['source_path']} {key}")
    count = sum(x["kind"] == "recipe" for x in records)
    if lock["recipe_count"] != count or lock["file_count"] != len(records):
        raise ValueError("manifest file counts do not match")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--revision", help="explicit source update; full lowercase 40-hex SHA only")
    parser.add_argument("--tree-file", type=Path, help="existing Git tree JSON for this exact revision")
    parser.add_argument("--cache", type=Path, help="optional existing raw tree; every file is hash-checked")
    parser.add_argument("--offline", action="store_true", help="verify without any network calls")
    parser.add_argument("--verify-only", action="store_true", help="audit lock/tree/files offline without modifying them")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.verify_only:
        if args.revision or args.tree_file or args.cache:
            raise ValueError("--verify-only does not accept revision, tree or cache changes")
        checked = verify_manifest(root)
        print(json.dumps({"verified": True, "revision": checked["revision"],
                          "recipe_count": checked["recipe_count"], "file_count": checked["file_count"]}))
        return 0
    existing = root / LOCK_PATH
    locked = json.loads(existing.read_text(encoding="utf-8")) if existing.exists() else None
    rev = revision(args.revision or (locked["revision"] if locked else DEFAULT_REVISION))
    local_tree = root / TREE_PATH
    if args.tree_file:
        tree = json.loads(args.tree_file.read_text(encoding="utf-8"))
    elif local_tree.exists() and (not locked or rev == locked["revision"]):
        tree = json.loads(local_tree.read_text(encoding="utf-8"))
    elif args.offline:
        raise ValueError("offline Git tree missing; use --tree-file for the pinned revision")
    else:
        tree = read_recursive_tree(rev)
    if args.tree_file and tree.get("sha") != rev:
        raise ValueError("provided tree SHA does not match requested fixed revision")
    manifest = synchronize(root, rev, tree, cache=args.cache, offline=args.offline, workers=args.workers)
    print(json.dumps({"revision": rev, "recipe_count": manifest["recipe_count"],
                      "file_count": manifest["file_count"], "offline": args.offline}, ensure_ascii=False))
    return 0


def read_recursive_tree(rev: str) -> dict:
    """The allowlist permits only the exact recursive=1 Git Trees query."""
    revision(rev)
    tree = json.loads(read_url(f"https://api.github.com/repos/{REPOSITORY}/git/trees/{rev}?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("truncated upstream tree")
    return tree


if __name__ == "__main__":
    raise SystemExit(main())
