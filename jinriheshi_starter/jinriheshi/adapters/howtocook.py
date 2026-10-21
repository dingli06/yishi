from __future__ import annotations

import copy
import re
import uuid
from pathlib import PurePosixPath
from typing import Any

from .. import ADAPTER_VERSION, SCHEMA_VERSION
from ..common import canonical_bytes, digest

NAMESPACE = uuid.UUID("82221d9a-a052-5ef5-9393-ec6d77d290a0")
SECTION_NAMES = {
    "ingredients": ("必备原料", "原料和工具", "所需原料", "所需材料"),
    "quantities": ("计算", "用量"),
    "steps": ("操作", "制作步骤", "制作过程", "做法"),
    "notes": ("附加内容", "注意事项", "小贴士"),
}


def section_kind(title: str) -> str:
    for name, markers in SECTION_NAMES.items():
        if any(marker in title for marker in markers):
            return name
    return "other"


def parse_markdown(text: str) -> dict[str, Any]:
    """保留二级章节全文和行号；顶层列表项的子步骤不被扔掉。"""
    lines = text.splitlines()
    h1 = next((line[2:].strip() for line in lines if line.startswith("# ")), "")
    title = re.sub(r"的做法\s*$", "", h1).strip()
    starts = [(i, line[3:].strip()) for i, line in enumerate(lines)
              if line.startswith("## ")]
    first = starts[0][0] if starts else len(lines)
    intro = "\n".join(line for line in lines[1:first]).strip()
    sections = []
    for index, (start, heading) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
        sections.append({"heading": heading, "kind": section_kind(heading),
                         "text": "\n".join(lines[start + 1:end]).strip(),
                         "line_start": start + 2, "line_end": end})
    steps = []
    for section in sections:
        if section["kind"] != "steps":
            continue
        # Subheadings belong to the following actions. A warning or preparation
        # paragraph before the first list item is also an executable block.
        # Keep nested lists inside their parent item, and do not parse Markdown
        # markers inside a fenced code block as new cooking instructions.
        groups: list[tuple[str, list[tuple[str, bool]]]] = []
        heading_stack: list[tuple[int, str]] = []
        current_heading = section["heading"]
        current_lines: list[tuple[str, bool]] = []
        fence_char: str | None = None
        fence_size = 0
        for line in section["text"].splitlines():
            fence = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            inside_fence = fence_char is not None
            if fence:
                marker = fence.group(1)
                if not inside_fence:
                    fence_char, fence_size = marker[0], len(marker)
                elif marker[0] == fence_char and len(marker) >= fence_size:
                    fence_char, fence_size = None, 0
                current_lines.append((line, False))
                continue
            heading = None if inside_fence else re.match(r"^(#{3,6})\s+(.+)$", line)
            if heading:
                if any(text.strip() for text, _ in current_lines):
                    groups.append((current_heading, current_lines))
                current_lines = []
                level, label = len(heading.group(1)), heading.group(2).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, label))
                current_heading = " / ".join([section["heading"]] + [x[1] for x in heading_stack])
                continue
            is_item = not inside_fence and bool(re.match(r"^(?:\d+[.)、]|[-*+])\s+", line))
            current_lines.append((line, is_item))
        if any(text.strip() for text, _ in current_lines):
            groups.append((current_heading, current_lines))
        for source_heading, body in groups:
            markers = [i for i, (_, is_item) in enumerate(body) if is_item]
            if not markers:
                markers = [0]
            elif any(line.strip() for line, _ in body[:markers[0]]):
                markers.insert(0, 0)
            for index, start in enumerate(markers):
                end = markers[index + 1] if index + 1 < len(markers) else len(body)
                block = "\n".join(line for line, _ in body[start:end]).strip()
                if body[start][1]:
                    block = re.sub(r"^(?:\d+[.)、]|[-*+])\s+", "", block)
                if block:
                    steps.append({"id": f"step_{len(steps) + 1:03d}",
                                  "position": len(steps) + 1, "text": block,
                                  "source_heading": source_heading})
    image_refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    return {"title": title, "intro": intro, "sections": sections,
            "steps": steps, "image_refs": image_refs}


class HowToCookAdapter:
    source_id = "howtocook"

    def normalize(self, *, raw: bytes, source: dict[str, Any],
                  overlay: dict[str, Any] | None,
                  identity: dict[str, Any]) -> dict[str, Any]:
        content = parse_markdown(raw.decode("utf-8"))
        original_key = f"howtocook:{source['source_path']}"
        source_key = identity.get("source_key_aliases", {}).get(original_key, original_key)
        title = (overlay or {}).get("title") or content.pop("title") or PurePosixPath(source["source_path"]).stem
        content.pop("title", None)
        recipe_id = "recipe_" + uuid.uuid5(NAMESPACE, source_key).hex
        dish_id = identity.get("dish_id_overrides", {}).get(original_key)
        dish_id = dish_id or "dish_" + uuid.uuid5(NAMESPACE, "dish:" + title).hex
        category = PurePosixPath(source["source_path"]).parts[1]
        recipe: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "recipe_id": recipe_id, "dish_id": dish_id,
            "title": title,
            "source": {"source_id": self.source_id, "source_key": original_key,
                       "source_path": source["source_path"], "revision": source["revision"],
                       "blob_sha": source["blob_sha"], "content_sha256": source["content_sha256"],
                       "url": source["source_url"], "raw_path": source["local_path"],
                       "license": "Unlicense", "adapter_version": ADAPTER_VERSION},
            "publication": {"state": "development" if overlay else "draft",
                            "reviewed_by": None, "reviewed_at": None},
            "source_category": category,
            "content": content,
            "ingredients": [],
            "tags": {"tastes": [], "cuisines": [], "textures": [],
                     "meal_form": "unknown", "standalone_meal": None},
            "equipment": {"required_all": [], "required_any": [],
                          "status": "unknown", "evidence": []},
            "time": {"source_text": None, "source_estimate_minutes": None,
                     "total_minutes": None, "active_minutes": None,
                     "prerequisites": [], "status": "unknown"},
            "servings": {"source_text": None, "min": None, "max": None,
                         "status": "unknown", "scaling_policy": "manual"},
            "nutrition": {"value": None, "status": "unknown"},
            "cost": {"value": None, "status": "unknown"},
            "tag_evidence": [],
            "review": {"status": "imported", "ingredient_completeness": "needs_review",
                       "issues": ["尚未完成结构化标注"], "reviewer": None,
                       "cooking_tested": False},
            "extensions": {},
        }
        if overlay:
            if overlay["source_sha256"] != source["content_sha256"]:
                raise ValueError(f"Stale overlay for {source['source_path']}; review new source before rebuilding")
            for key in ("ingredients", "tags", "equipment", "time", "review", "tag_evidence"):
                recipe[key] = copy.deepcopy(overlay[key])
            quantity_sections = [s["text"] for s in content["sections"] if s["kind"] == "quantities"]
            recipe["servings"]["source_text"] = "\n".join(quantity_sections) or None
        # Bind the version to the full effective record, including normalized
        # source provenance and resolved identity. This also captures parser or
        # default-field changes, rather than reusing an old version for new data.
        # The version itself is excluded from its hash, and no clock is involved.
        recipe["recipe_version"] = "rv_" + digest(canonical_bytes(recipe))[:24]
        return recipe
