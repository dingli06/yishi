-- 可重建的菜谱镜像；用户、反馈、会话的生产表由后续服务任务实现。
PRAGMA foreign_keys = ON;
CREATE TABLE dishes (
  dish_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL
);
CREATE TABLE recipe_versions (
  recipe_id TEXT NOT NULL,
  recipe_version TEXT NOT NULL,
  dish_id TEXT NOT NULL REFERENCES dishes(dish_id),
  title TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  publication_state TEXT NOT NULL CHECK(publication_state IN ('draft','development','published','withdrawn')),
  payload TEXT NOT NULL CHECK(json_valid(payload)),
  PRIMARY KEY(recipe_id, recipe_version),
  UNIQUE(source_id, source_path, recipe_version)
);
CREATE INDEX idx_recipes_dish ON recipe_versions(dish_id);
CREATE INDEX idx_recipes_publication ON recipe_versions(publication_state);
CREATE TABLE dataset_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version = 1;
