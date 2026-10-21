from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import read_json, root_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="今日何食数据与推荐开发工具")
    parser.add_argument("--root", type=Path, default=root_path())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build", help="离线解析原文、合并标注并生成数据")
    commands.add_parser("validate", help="JSON Schema与来源、证据、语义检查")
    choice = commands.add_parser("recommend", help="规则参考实现；默认仅生产已发布数据")
    choice.add_argument("--request", type=Path, required=True)
    choice.add_argument("--mode", choices=["production", "development"], default="production")
    choice.add_argument("--seed", type=int)
    sql = commands.add_parser("export-sqlite", help="导出可重建的开发数据库镜像")
    sql.add_argument("--output", type=Path, default=Path("data/generated/recipes.sqlite"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "build":
            from .build import build
            result = build(root)
        elif args.command == "validate":
            from .validate import validate_dataset
            result = validate_dataset(root)
        elif args.command == "recommend":
            from .recommend import recommend
            from .storage import JsonRecipeRepository
            from .validate import schema_errors, validate_request
            request_path = args.request if args.request.is_absolute() else root / args.request
            request = read_json(request_path)
            errors = validate_request(root, request)
            if errors:
                raise ValueError("Invalid request: " + "; ".join(errors))
            dictionary = {x["id"]: x for x in read_json(root / "data/dictionaries/ingredients.json")["items"]}
            result = recommend(JsonRecipeRepository(root / "data/generated/recipes.jsonl").all(),
                               request, dictionary, mode=args.mode, seed=args.seed)
            errors = schema_errors(root, "recommendation_response.schema.json", result)
            if errors:
                raise ValueError("Invalid response: " + "; ".join(errors))
        else:
            from .sqlite_export import export_sqlite
            output = args.output if args.output.is_absolute() else root / args.output
            result = export_sqlite(root, output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("ok") is False else 0
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
