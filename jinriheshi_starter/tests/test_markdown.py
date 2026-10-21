"""Preserve executable content and preconditions when flattening Markdown."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import unittest

from jinriheshi.adapters.howtocook import parse_markdown
from jinriheshi.adapters.howtocook import HowToCookAdapter


class MarkdownTests(unittest.TestCase):
    def test_preconditions_before_first_list_item_are_preserved(self):
        source = "# 菜\n\n## 操作\n\n开火前将开水放在手边。\n必须使用处理好的鱼。\n\n1. 开火\n2. 加料\n"
        steps = parse_markdown(source)["steps"]
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]["text"], "开火前将开水放在手边。\n必须使用处理好的鱼。")
        self.assertEqual(steps[1]["text"], "开火")

    def test_subsection_heading_belongs_to_following_step(self):
        source = "# 菜\n\n## 操作\n\n### 腌制（提前一晚）\n\n1. 加盐\n\n### 烹饪\n\n1. 下锅\n"
        steps = parse_markdown(source)["steps"]
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0]["source_heading"], "操作 / 腌制（提前一晚）")
        self.assertNotIn("烹饪", steps[0]["text"])
        self.assertEqual(steps[1]["source_heading"], "操作 / 烹饪")

    def test_nested_items_and_html_warning_are_preserved(self):
        source = "# 菜\n\n## 操作\n1. 切菜\n\n  - 注意：刀口向外\n  - <!-- 勿直接用手碰刀刃 -->\n\n2. 下锅\n"
        steps = parse_markdown(source)["steps"]
        self.assertEqual(len(steps), 2)
        self.assertIn("- 注意：刀口向外", steps[0]["text"])
        self.assertIn("<!-- 勿直接用手碰刀刃 -->", steps[0]["text"])

    def test_fenced_content_is_not_parsed_as_headings_or_list(self):
        source = "# 菜\n\n## 操作\n1. 查看用量\n\n```text\n### 不是小节\n1. 不是新步骤\n```\n\n2. 混合\n"
        steps = parse_markdown(source)["steps"]
        self.assertEqual(len(steps), 2)
        self.assertIn("### 不是小节", steps[0]["text"])
        self.assertIn("1. 不是新步骤", steps[0]["text"])

    def test_real_corpus_keeps_every_nonempty_operation_line(self):
        root = Path(__file__).resolve().parents[1]
        lock = json.loads((root / "data/sources/howtocook.lock.json").read_text(encoding="utf-8"))
        recipes = [x for x in lock["files"] if x["kind"] == "recipe"]
        self.assertGreaterEqual(len(recipes), 30)
        for source in recipes:
            with self.subTest(source=source["source_path"]):
                parsed = parse_markdown((root / source["local_path"]).read_text(encoding="utf-8"))
                rendered = "\n".join(x["source_heading"] + "\n" + x["text"] for x in parsed["steps"])
                for section in parsed["sections"]:
                    if section["kind"] != "steps":
                        continue
                    for line in section["text"].splitlines():
                        # Heading markup and the first list marker may be represented
                        # structurally. Every actual word must survive in a step or its heading.
                        text = re.sub(r"^#{3,6}\s+", "", line.strip())
                        text = re.sub(r"^(?:\d+[.)、]|[-*+])\s+", "", text)
                        if text:
                            self.assertIn(text, rendered)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = HowToCookAdapter()
        self.raw = "# 示例的做法\n\n## 操作\n1. 准备材料\n".encode()
        self.source = {
            "source_path": "dishes/vegetable_dish/示例.md", "revision": "a" * 40,
            "content_sha256": hashlib.sha256(self.raw).hexdigest(),
            "blob_sha": hashlib.sha1(b"blob " + str(len(self.raw)).encode() + b"\0" + self.raw).hexdigest(),
            "source_url": "https://example.invalid/source", "local_path": "data/raw/example.md",
        }

    def normalize(self, source=None, identity=None):
        return self.adapter.normalize(raw=self.raw, source=source or self.source,
                                      overlay=None, identity=identity or {})

    def test_identical_effective_input_has_identical_version(self):
        self.assertEqual(self.normalize(), self.normalize())

    def test_each_provenance_change_has_a_new_version(self):
        original = self.normalize()
        for field, value in [("revision", "b" * 40), ("source_url", "https://example.invalid/new"),
                             ("local_path", "data/raw/renamed.md"), ("blob_sha", "c" * 40)]:
            with self.subTest(field=field):
                changed = self.normalize(source={**self.source, field: value})
                self.assertEqual(original["recipe_id"], changed["recipe_id"])
                self.assertNotEqual(original["recipe_version"], changed["recipe_version"])

    def test_identity_override_changes_record_version(self):
        original = self.normalize()
        changed = self.normalize(identity={"dish_id_overrides": {
            "howtocook:" + self.source["source_path"]: "dish_" + "1" * 32,
        }})
        self.assertNotEqual(original["dish_id"], changed["dish_id"])
        self.assertNotEqual(original["recipe_version"], changed["recipe_version"])

    def test_version_is_content_hash_of_the_record_without_itself(self):
        from jinriheshi.common import canonical_bytes, digest
        record = self.normalize()
        version = record.pop("recipe_version")
        self.assertEqual(version, "rv_" + digest(canonical_bytes(record))[:24])


if __name__ == "__main__":
    unittest.main()
