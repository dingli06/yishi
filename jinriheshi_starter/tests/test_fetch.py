"""Regression tests for source integrity and safe, repeatable imports."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

_PATH = Path(__file__).resolve().parents[1] / "scripts/fetch_howtocook.py"
_SPEC = importlib.util.spec_from_file_location("fetch_howtocook", _PATH)
fetch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch)


class FetchTests(unittest.TestCase):
    def make_tree(self, contents):
        return {"sha": fetch.DEFAULT_REVISION, "truncated": False, "tree": [
            {"path": name, "type": "blob", "mode": "100644", "sha": fetch.blob_sha(body)}
            for name, body in contents.items()
        ]}

    def test_known_git_blob_algorithm(self):
        self.assertEqual(fetch.blob_sha(b"test content\n"), "d670460b4b4aece5915caf5c68d12f560a9fe3e4")

    def test_source_path_rejects_traversal_images_and_template(self):
        for name in ["../LICENSE", "/LICENSE", "dishes/../LICENSE", "dishes/x.png",
                     "dishes/template/示例菜.md", "dishes\\x.md", "dishes//x.md"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                fetch.source_path(name)

    def test_network_allowlist(self):
        base = "https://raw.githubusercontent.com/Anduin2017/HowToCook/" + fetch.DEFAULT_REVISION
        self.assertTrue(fetch.allowed_url(base + "/LICENSE"))
        self.assertTrue(fetch.allowed_url(base + "/dishes/x.md"))
        self.assertFalse(fetch.allowed_url(base + "/dishes/x.jpg"))
        self.assertFalse(fetch.allowed_url(base + "/dishes/%2e%2e/LICENSE"))
        self.assertFalse(fetch.allowed_url(base.replace("https://", "http://") + "/LICENSE"))
        self.assertFalse(fetch.allowed_url("https://example.com/"))
        self.assertFalse(fetch.allowed_url(base.replace(fetch.DEFAULT_REVISION, "master") + "/LICENSE"))
        self.assertFalse(fetch.allowed_url(base + "/LICENSE?token=anything"))
        api = "https://api.github.com/repos/Anduin2017/HowToCook/git/trees/" + fetch.DEFAULT_REVISION
        self.assertTrue(fetch.allowed_url(api + "?recursive=1"))
        self.assertFalse(fetch.allowed_url(api + "?anything=1"))

    def test_template_is_not_counted(self):
        tree = self.make_tree({"LICENSE": b"license", "README.md": b"readme",
                               "dishes/a.md": b"a", "dishes/template/a.md": b"template"})
        self.assertEqual(len(fetch.select_files(tree)), 3)

    def test_offline_idempotence_and_read_only_verification(self):
        contents = {"LICENSE": b"license", "README.md": b"readme", "dishes/a.md": b"# A\n"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"; cache = Path(temp) / "cache"
            for name, content in contents.items():
                path = cache / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
            tree = self.make_tree(contents)
            with patch.object(fetch, "read_url", side_effect=AssertionError("network called")):
                first = fetch.synchronize(root, fetch.DEFAULT_REVISION, tree, cache=cache, offline=True)
                original_lock = (root / fetch.LOCK_PATH).read_bytes()
                second = fetch.synchronize(root, fetch.DEFAULT_REVISION, tree, offline=True)
                self.assertEqual(first, second)
                self.assertEqual(original_lock, (root / fetch.LOCK_PATH).read_bytes())
                before = {str(p): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
                fetch.verify_manifest(root)
                self.assertEqual(before, {str(p): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()})

    def test_corruption_does_not_repair_or_publish_a_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); rev = fetch.DEFAULT_REVISION
            source = root / f"data/raw/howtocook/{rev}/dishes/a.md"
            source.parent.mkdir(parents=True); source.write_bytes(b"edited")
            entry = {"path": "dishes/a.md", "sha": fetch.blob_sha(b"original")}
            with self.assertRaises(ValueError):
                fetch.ensure_file(root, rev, entry, None, True)
            self.assertEqual(source.read_bytes(), b"edited")
            self.assertFalse((root / fetch.LOCK_PATH).exists())

    def test_missing_file_cannot_publish_partial_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / fetch.LOCK_PATH).parent.mkdir(parents=True)
            (root / fetch.LOCK_PATH).write_bytes(b"old lock marker")
            tree = self.make_tree({"LICENSE": b"license", "README.md": b"readme", "dishes/a.md": b"a"})
            with self.assertRaises(RuntimeError):
                fetch.synchronize(root, fetch.DEFAULT_REVISION, tree, offline=True)
            self.assertEqual((root / fetch.LOCK_PATH).read_bytes(), b"old lock marker")

    def test_manifest_tampering_is_detected(self):
        contents = {"LICENSE": b"license", "README.md": b"readme", "dishes/a.md": b"A"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"; cache = Path(temp) / "cache"
            for name, body in contents.items():
                path = cache / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body)
            fetch.synchronize(root, fetch.DEFAULT_REVISION, self.make_tree(contents), cache=cache, offline=True)
            lock = json.loads((root / fetch.LOCK_PATH).read_text())
            lock["files"][0]["content_sha256"] = "0" * 64
            (root / fetch.LOCK_PATH).write_text(json.dumps(lock))
            with self.assertRaises(ValueError):
                fetch.verify_manifest(root)


if __name__ == "__main__":
    unittest.main()
