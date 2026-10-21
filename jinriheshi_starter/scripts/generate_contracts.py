"""可重复生成 JSON Schema 和 HTTP 契约。字段修改需同步版本与迁移说明。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def obj(props, required=None):
    return {"type": "object", "properties": props,
            "required": list(props) if required is None else required,
            "additionalProperties": False}


def enum(*values): return {"enum": list(values)}
def arr(items, **extra): return {"type": "array", "items": items, **extra}
def nullable(item): return {"anyOf": [item, {"type": "null"}]}
def ref(name): return {"$ref": "#/$defs/" + name}
STRING = {"type": "string"}
TEXT = {"type": "string", "minLength": 1}
STRINGS = arr(TEXT, uniqueItems=True)
NULLTEXT = nullable(TEXT)
IDENTIFIER = {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}
IDS = arr(IDENTIFIER, uniqueItems=True)
RANGE = obj({"min": {"type": "number", "minimum": 0},
             "max": {"type": "number", "exclusiveMinimum": 0}})
EVIDENCE = obj({"quote": TEXT, "section": enum("ingredients", "quantities", "steps", "intro", "notes")})
SCHEMA_BASE = {"$schema": "https://json-schema.org/draft/2020-12/schema"}

INGREDIENT = obj({
    "ingredient_id": IDENTIFIER, "source_name": TEXT,
    "role": enum("main", "seasoning", "other"),
    "requirement": enum("required", "optional", "alternative", "unknown"),
    "quantity_text": NULLTEXT, "alternative_group": NULLTEXT,
    "evidence": arr(EVIDENCE, minItems=1),
})
TAGS = obj({"tastes": IDS, "cuisines": IDS, "textures": IDS,
            "meal_form": enum("dish", "staple", "soup", "breakfast", "drink", "dessert", "condiment", "semi_finished", "unknown"),
            "standalone_meal": nullable({"type": "boolean"})})
EQUIPMENT = obj({"required_all": IDS, "required_any": arr(IDS, minItems=0),
                 "status": enum("unknown", "agent_checked", "needs_review", "verified"),
                 "evidence": arr(EVIDENCE)})
TIME = obj({"source_text": NULLTEXT, "source_estimate_minutes": nullable(RANGE),
            "total_minutes": nullable(RANGE), "active_minutes": nullable(RANGE),
            "prerequisites": STRINGS,
            "status": enum("source_estimate", "unknown", "verified")})
REVIEW = obj({"status": enum("imported", "agent_checked", "needs_review", "approved"),
              "ingredient_completeness": enum("agent_checked", "needs_review", "verified"),
              "issues": arr(TEXT), "reviewer": NULLTEXT, "cooking_tested": {"type": "boolean"}})

RECIPE = {**SCHEMA_BASE, "$id": "urn:jinriheshi:schema:recipe:1.0.0",
          "title": "Jinriheshi recipe version", **obj({
    "schema_version": {"const": "1.0.0"},
    "recipe_id": {"type": "string", "pattern": "^recipe_[0-9a-f]{32}$"},
    "dish_id": {"type": "string", "pattern": "^dish_[0-9a-f]{32}$"},
    "recipe_version": {"type": "string", "pattern": "^rv_[0-9a-f]{24}$"},
    "title": TEXT,
    "source": obj({"source_id": IDENTIFIER, "source_key": TEXT, "source_path": TEXT,
                   "revision": TEXT,
                   "blob_sha": nullable({"type": "string", "pattern": "^[0-9a-f]{40}$"}),
                   "content_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                   "url": {"type": "string", "format": "uri"}, "raw_path": TEXT,
                   "license": TEXT, "adapter_version": TEXT}),
    "publication": obj({"state": enum("draft", "development", "published", "withdrawn"),
                        "reviewed_by": NULLTEXT,
                        "reviewed_at": nullable({"type": "string", "format": "date-time"})}),
    "source_category": TEXT,
    "content": obj({"intro": STRING,
                    "sections": arr(obj({"heading": TEXT, "kind": enum("ingredients", "quantities", "steps", "notes", "other"),
                                         "text": STRING, "line_start": {"type": "integer", "minimum": 1},
                                         "line_end": {"type": "integer", "minimum": 1}})),
                    "steps": arr(obj({"id": IDENTIFIER, "position": {"type": "integer", "minimum": 1},
                                      "text": TEXT, "source_heading": TEXT})),
                    "image_refs": arr(STRING)}),
    "ingredients": arr(INGREDIENT), "tags": TAGS, "equipment": EQUIPMENT, "time": TIME,
    "servings": obj({"source_text": NULLTEXT, "min": nullable({"type": "number", "exclusiveMinimum": 0}),
                     "max": nullable({"type": "number", "exclusiveMinimum": 0}),
                     "status": enum("unknown", "source_estimate", "verified"),
                     "scaling_policy": enum("manual", "linear_verified")}),
    "nutrition": obj({"value": {"type": "null"}, "status": {"const": "unknown"}}),
    "cost": obj({"value": {"type": "null"}, "status": {"const": "unknown"}}),
    "tag_evidence": arr(obj({"field": TEXT, "value": {"type": ["string", "boolean"]}, "quote": TEXT,
                             "section": enum("ingredients", "quantities", "steps", "intro", "notes")})),
    "review": REVIEW,
    "extensions": {"type": "object"},
})}

CONSTRAINTS = obj({
    "max_total_minutes": nullable({"type": "integer", "minimum": 1, "maximum": 10080}),
    "available_equipment": nullable(IDS),
    "pantry_mode": enum("any", "only_owned", "allow_missing"),
    "owned_ingredients": IDS,
    "max_missing_ingredients": nullable({"type": "integer", "minimum": 0}),
    "required_ingredients": IDS, "excluded_ingredients": IDS,
    "cuisines_only": IDS,
    "meal_forms": arr(enum("dish", "staple", "soup", "breakfast", "drink", "dessert", "condiment", "semi_finished"), uniqueItems=True),
    "standalone_meal": nullable({"type": "boolean"}),
    "servings": nullable({"type": "integer", "minimum": 1, "maximum": 20}),
    "confirmed_prerequisites": STRINGS,
}, required=[])
PREFERENCES = obj({"tastes": IDS, "cuisines": IDS, "textures": IDS,
                   "priority_ingredients": IDS,
                   "novelty": enum("any", "familiar", "new")}, required=[])
CONTEXT = obj({"seen_dish_ids": STRINGS, "recently_cooked_dish_ids": STRINGS,
               "favorite_dish_ids": STRINGS}, required=[])
REQUEST = {**SCHEMA_BASE, "$id": "urn:jinriheshi:schema:recommendation-request:1.0.0",
           **obj({"schema_version": {"const": "1.0.0"}, "constraints": CONSTRAINTS,
                  "preferences": PREFERENCES, "context": CONTEXT}, required=["schema_version"])}

CARD = obj({"recipe_id": TEXT, "recipe_version": TEXT, "dish_id": TEXT, "title": TEXT,
            "publication_state": enum("development", "published"), "review_status": TEXT,
            "source_url": {"type": "string", "format": "uri"},
            "source_estimate_minutes": nullable(RANGE), "total_minutes": nullable(RANGE),
            "time_status": enum("source_estimate", "unknown", "verified"),
            "meal_form": STRING, "standalone_meal": nullable({"type": "boolean"}),
            "missing_ingredient_ids": nullable(IDS), "selected_ingredient_ids": IDS,
            "omitted_optional_ingredient_ids": IDS, "pantry_match_scope": enum("not_checked", "ingredient_types_only"),
            "reasons": arr(TEXT), "notices": arr(TEXT)})
RESPONSE = {**SCHEMA_BASE, "$id": "urn:jinriheshi:schema:recommendation-response:1.0.0",
            **obj({"schema_version": {"const": "1.0.0"}, "mode": enum("production", "development"),
                   "status": enum("ok", "no_candidate"), "candidate_count": {"type": "integer", "minimum": 0},
                   "selected": nullable(CARD), "exclusion_counts": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}},
                   "suggestions": arr(obj({"code": TEXT, "message": TEXT})), "notices": arr(TEXT)})}

EVENT = {**SCHEMA_BASE, "$id": "urn:jinriheshi:schema:event:1.0.0", **obj({
    "schema_version": {"const": "1.0.0"},
    "event_id": {"type": "string", "minLength": 16, "maxLength": 128},
    "session_id": TEXT, "recommendation_id": TEXT, "recipe_id": TEXT, "recipe_version": TEXT,
    "type": enum("shown", "skip", "accept", "favorite", "unfavorite", "cooked", "reject"),
    "reason": nullable(enum("not_today", "too_much_work", "ingredients_inconvenient", "recently_ate", "always_dislike", "just_browsing")),
    "occurred_at": {"type": "string", "format": "date-time"},
    "scope": enum("session", "recent", "permanent"),
    "confirmed_permanent": {"type": "boolean"},
    "permanent_excluded_ingredient_ids": IDS,
}), "allOf": [
    {"if": {"properties": {"scope": {"const": "permanent"}}},
     "then": {"properties": {"confirmed_permanent": {"const": True}, "reason": {"const": "always_dislike"}, "type": {"const": "reject"},
                               "permanent_excluded_ingredient_ids": {"minItems": 1}}},
     "else": {"properties": {"confirmed_permanent": {"const": False}, "permanent_excluded_ingredient_ids": {"maxItems": 0}}}},
    {"if": {"properties": {"type": {"enum": ["shown", "skip", "accept", "favorite", "unfavorite", "cooked"]}}},
     "then": {"properties": {"reason": {"type": "null"}, "confirmed_permanent": {"const": False}}}}
]}


def write(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http_response(description, schema):
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def main():
    for name, schema in [("recipe", RECIPE), ("recommendation_request", REQUEST),
                         ("recommendation_response", RESPONSE), ("event", EVENT)]:
        write(f"schemas/{name}.schema.json", schema)
    error = obj({"code": TEXT, "message": TEXT, "request_id": TEXT})
    auth = [{"SessionToken": []}]
    idempotency = {"name": "Idempotency-Key", "in": "header", "required": True,
                   "schema": {"type": "string", "minLength": 16, "maxLength": 128},
                   "description": "同用户、路由和key：同请求体重放同响应；不同体返回409。至少保留24小时。"}
    session_path = {"name": "session_id", "in": "path", "required": True, "schema": TEXT}
    public_ingredient = obj({"ingredient_id": IDENTIFIER, "name": TEXT, "quantity_text": NULLTEXT,
                             "requirement": enum("required", "optional", "alternative", "unknown"),
                             "alternative_group": NULLTEXT})
    capability = obj({"enabled": {"type": "boolean"}, "reviewed_candidate_count": {"type": "integer", "minimum": 0},
                      "reason": NULLTEXT})
    options_response = obj({"schema_version": {"const": "1.0.0"},
                            "published_recipe_count": {"type": "integer", "minimum": 0},
                            "capabilities": {"type": "object", "additionalProperties": capability},
                            "groups": arr(obj({"id": TEXT, "label": TEXT, "selection": enum("single", "multiple"),
                                               "options": arr(obj({"value": TEXT, "label": TEXT, "enabled": {"type": "boolean"}}))})),
                            "defaults": obj({"constraints": CONSTRAINTS, "preferences": PREFERENCES})})
    public_recipe = obj({"recipe_id": TEXT, "recipe_version": TEXT, "dish_id": TEXT, "title": TEXT,
                         "image": nullable(obj({"url": {"type": "string", "format": "uri"}, "alt": TEXT, "attribution": NULLTEXT})),
                         "ingredients": arr(public_ingredient, minItems=1),
                         "steps": arr(obj({"position": {"type": "integer", "minimum": 1}, "text": TEXT}), minItems=1),
                         "tags": TAGS, "time": TIME,
                         "servings": obj({"min": nullable({"type": "number"}), "max": nullable({"type": "number"}), "display_text": NULLTEXT}),
                         "source": obj({"name": TEXT, "url": {"type": "string", "format": "uri"}, "license": TEXT}),
                         "notices": arr(TEXT)})
    doc = {
        "openapi": "3.1.0",
        "info": {"title": "今日何食 P0 API（待开发契约）", "version": "0.1.0",
                 "description": "本包只有离线数据工具和纯规则参考，没有已运行的HTTP服务。生产状态和用户历史由服务端决定。"},
        "servers": [{"url": "/"}],
        "components": {"securitySchemes": {"SessionToken": {"type": "http", "scheme": "bearer"}},
                       "schemas": {"Error": error, "Options": options_response, "PublicRecipe": public_recipe}},
        "paths": {
            "/v1/options": {"get": {"operationId": "getOptions", "summary": "返回枚举、默认值及已发布数据覆盖能力",
                "responses": {"200": http_response("选项及能力，不启用数据不足的严格筛选", {"$ref": "#/components/schemas/Options"})}}},
            "/v1/sessions": {"post": {"operationId": "createSession", "security": auth,
                "parameters": [idempotency],
                "requestBody": {"required": True, "content": {"application/json": {"schema": obj({"constraints": CONSTRAINTS, "preferences": PREFERENCES}, required=[])}}},
                "responses": {"201": http_response("创建推荐会话", obj({"session_id": TEXT, "revision": {"type": "integer", "minimum": 1}})),
                              "422": http_response("无效条件", error), "409": http_response("幂等键冲突", error)}}},
            "/v1/sessions/{session_id}/recommendations": {"post": {"operationId": "nextRecommendation", "security": auth,
                "parameters": [session_path, idempotency],
                "requestBody": {"required": True, "content": {"application/json": {"schema": obj({"expected_revision": {"type": "integer", "minimum": 1}})}}},
                "description": "服务端读取会话和历史，生产仅published。原子选择并记录曝光；同key重试不能跳到下一道。客户端不能传mode、seed或context。",
                "responses": {"200": http_response("结果或明确空结果", obj({"recommendation_id": NULLTEXT, "session_revision": {"type": "integer", "minimum": 1}, "result": {"$ref": "../schemas/recommendation_response.schema.json"}})),
                              "409": http_response("幂等键或会话版本冲突", error), "404": http_response("会话不存在或无权访问", error)}}},
            "/v1/recipes/{recipe_id}/versions/{recipe_version}": {"get": {"operationId": "getRecipeVersion",
                "parameters": [{"name": n, "in": "path", "required": True, "schema": TEXT} for n in ["recipe_id", "recipe_version"]],
                "description": "返回经过展示审核的精确版本；下架版本返回410。不暴露原始路径、内部审核备注或未授权图像。",
                "responses": {"200": http_response("公开菜谱详情投影", {"$ref": "#/components/schemas/PublicRecipe"}),
                              "404": http_response("未发布或不存在", error), "410": http_response("已下架", error)}}},
            "/v1/events": {"post": {"operationId": "recordFeedback", "security": auth,
                "parameters": [idempotency],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "../schemas/event.schema.json"}}}},
                "description": "event_id另设唯一约束；校验会话归属及推荐版本。accept不能写入cooked，permanent必须显式确认。",
                "responses": {"200": http_response("幂等事件回执", obj({"event_id": TEXT, "applied": {"type": "boolean"}})),
                              "409": http_response("同ID不同请求冲突", error), "422": http_response("事件不合法", error)}}},
        },
    }
    write("contracts/openapi.json", doc)
    print("Generated 4 JSON Schemas and contracts/openapi.json")


if __name__ == "__main__":
    main()
