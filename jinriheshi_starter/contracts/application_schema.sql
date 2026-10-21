-- Persistent user/application state. This database is separate from the rebuildable recipe mirror.
-- The executable source of this migration currently lives in jinriheshi/application.py.
-- Kept here as the contract entry point for T03; schema version is PRAGMA user_version = 1.

-- Tables: subjects, sessions, recommendations, idempotency, events, favorites, subject_settings.
-- Run through ApplicationRepository so foreign keys, JSON checks and indexes are created together.
