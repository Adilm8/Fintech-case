-- Initial schema for BCC Business Shield prod mode.

CREATE TABLE companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  bin TEXT NOT NULL UNIQUE,
  iik TEXT NOT NULL,
  bik TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  company_id TEXT REFERENCES companies(id),
  login TEXT NOT NULL UNIQUE COLLATE NOCASE,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('accountant','director','analyst')),
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  CHECK ((role = 'analyst') = (company_id IS NULL))
);

CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX ix_sessions_user ON sessions(user_id);

CREATE TABLE import_batches (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies(id),
  created_by INTEGER NOT NULL REFERENCES users(id),
  source TEXT NOT NULL CHECK (source IN ('1c','csv')),
  filename TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,
  total INTEGER NOT NULL,
  created_count INTEGER NOT NULL,
  failed_count INTEGER NOT NULL,
  errors_json TEXT NOT NULL DEFAULT '[]',
  is_forced INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_batches_company_sha ON import_batches(company_id, file_sha256)
  WHERE is_forced = 0;
CREATE INDEX ix_batches_company_sha ON import_batches(company_id, file_sha256);

CREATE TABLE payments (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies(id),
  source TEXT NOT NULL CHECK (source IN ('manual','1c','csv','seed')),
  batch_id TEXT REFERENCES import_batches(id),
  line_no INTEGER,
  doc_number TEXT NOT NULL DEFAULT '',
  doc_date TEXT,
  recipient_name TEXT NOT NULL,
  recipient_bin TEXT NOT NULL,
  recipient_iik TEXT NOT NULL,
  recipient_bik TEXT NOT NULL,
  amount_tiyn INTEGER NOT NULL CHECK (amount_tiyn > 0),
  purpose TEXT NOT NULL DEFAULT '',
  kbe TEXT NOT NULL DEFAULT '',
  knp TEXT NOT NULL DEFAULT '',
  request_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN
    ('checked','pending_approval','approved','rejected','postponed','signed','cancelled')),
  check_id TEXT,
  approval_id TEXT,
  accountant_ack INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  signed_by INTEGER REFERENCES users(id),
  signed_at TEXT,
  paid_at TEXT
);
CREATE INDEX ix_pay_company_status ON payments(company_id, status);
CREATE INDEX ix_pay_company_bin ON payments(company_id, recipient_bin);
CREATE INDEX ix_pay_batch ON payments(batch_id);
CREATE INDEX ix_pay_sha ON payments(company_id, request_sha256);

CREATE TABLE checks (
  id TEXT PRIMARY KEY,
  payment_id TEXT NOT NULL REFERENCES payments(id),
  request_sha256 TEXT NOT NULL,
  ruleset_version TEXT NOT NULL,
  verdict TEXT NOT NULL,
  score INTEGER NOT NULL,
  signal_ids_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  trigger TEXT NOT NULL CHECK (trigger IN ('create','edit','recheck','sign','resume')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX ix_checks_payment ON checks(payment_id);

CREATE TABLE approvals (
  id TEXT PRIMARY KEY,
  payment_id TEXT NOT NULL REFERENCES payments(id),
  check_id TEXT NOT NULL REFERENCES checks(id),
  request_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','approved','rejected','superseded')),
  accountant_note TEXT NOT NULL DEFAULT '',
  director_comment TEXT,
  trust_account INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  decided_by INTEGER REFERENCES users(id),
  decided_at TEXT
);
CREATE UNIQUE INDEX ux_appr_pending ON approvals(payment_id) WHERE status = 'pending';
CREATE INDEX ix_appr_payment ON approvals(payment_id);

CREATE TABLE trusted_accounts (
  id INTEGER PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies(id),
  recipient_bin TEXT NOT NULL,
  recipient_iik TEXT NOT NULL,
  approval_id TEXT REFERENCES approvals(id),
  director_comment TEXT NOT NULL,
  decided_by INTEGER NOT NULL REFERENCES users(id),
  decided_at TEXT NOT NULL,
  revoked_at TEXT,
  revoked_by INTEGER REFERENCES users(id)
);
CREATE UNIQUE INDEX ux_trusted_active ON trusted_accounts(company_id, recipient_bin, recipient_iik)
  WHERE revoked_at IS NULL;

CREATE TABLE suppliers (
  id INTEGER PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES companies(id),
  bin TEXT NOT NULL,
  name TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_payment_at TEXT,
  requisites_changed_at TEXT,
  UNIQUE (company_id, bin)
);

CREATE TABLE supplier_accounts (
  id INTEGER PRIMARY KEY,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  iik TEXT NOT NULL,
  bik TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_used_at TEXT NOT NULL,
  payments_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE (supplier_id, iik)
);

CREATE TABLE supplier_changes (
  id INTEGER PRIMARY KEY,
  supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
  kind TEXT NOT NULL CHECK (kind IN ('account_added','bank_changed','name_changed')),
  old_value TEXT,
  new_value TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  payment_id TEXT REFERENCES payments(id)
);
CREATE INDEX ix_supplier_changes_supplier ON supplier_changes(supplier_id);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  user_id INTEGER,
  user_login TEXT,
  role TEXT,
  company_id TEXT,
  action TEXT NOT NULL,
  payment_id TEXT,
  approval_id TEXT,
  check_id TEXT,
  batch_id TEXT,
  request_sha256 TEXT,
  ruleset_version TEXT,
  verdict TEXT,
  signal_ids_json TEXT NOT NULL DEFAULT '[]',
  details_json TEXT NOT NULL DEFAULT '{}',
  prev_hash TEXT NOT NULL,
  entry_hash TEXT NOT NULL
);
CREATE INDEX ix_audit_company ON audit_log(company_id);
CREATE INDEX ix_audit_payment ON audit_log(payment_id);
CREATE INDEX ix_audit_action ON audit_log(action);

-- Append-only enforcement triggers for audit_log, checks, and supplier_changes.
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TRIGGER checks_no_update BEFORE UPDATE ON checks
  BEGIN SELECT RAISE(ABORT, 'checks is append-only'); END;
CREATE TRIGGER checks_no_delete BEFORE DELETE ON checks
  BEGIN SELECT RAISE(ABORT, 'checks is append-only'); END;

CREATE TRIGGER supplier_changes_no_update BEFORE UPDATE ON supplier_changes
  BEGIN SELECT RAISE(ABORT, 'supplier_changes is append-only'); END;
CREATE TRIGGER supplier_changes_no_delete BEFORE DELETE ON supplier_changes
  BEGIN SELECT RAISE(ABORT, 'supplier_changes is append-only'); END;

PRAGMA user_version = 1;
