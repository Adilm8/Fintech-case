-- Account security schema: forced password change flag and password-change rate limiting.

ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0
  CHECK (must_change_password IN (0, 1));

CREATE TABLE password_change_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  attempted_at TEXT NOT NULL
);
CREATE INDEX ix_password_change_attempts_user_time
  ON password_change_attempts(user_id, attempted_at);

PRAGMA user_version = 3;
