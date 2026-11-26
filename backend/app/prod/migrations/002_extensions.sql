-- Extension schema for profile preferences, company settings, and notification read state.

ALTER TABLE users ADD COLUMN default_lang TEXT NOT NULL DEFAULT 'ru'
  CHECK (default_lang IN ('ru', 'kk', 'en'));

CREATE TABLE company_settings (
  company_id TEXT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
  notify_on TEXT NOT NULL DEFAULT 'red_yellow' CHECK (notify_on IN ('red', 'red_yellow')),
  approval_threshold_tiyn INTEGER CHECK (approval_threshold_tiyn IS NULL OR approval_threshold_tiyn > 0),
  updated_at TEXT NOT NULL
);

CREATE TABLE notification_reads (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  notification_id TEXT NOT NULL,
  read_at TEXT NOT NULL,
  PRIMARY KEY (user_id, notification_id)
);
CREATE INDEX ix_notification_reads_user ON notification_reads(user_id);

PRAGMA user_version = 2;
