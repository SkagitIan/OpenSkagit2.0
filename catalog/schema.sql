CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  base_url TEXT NOT NULL,
  domains TEXT NOT NULL,
  supports TEXT NOT NULL,
  config TEXT,
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queries (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  case_file_id TEXT,
  source_id TEXT NOT NULL,
  source_name TEXT,
  domain TEXT,
  query_type TEXT,
  query_params TEXT NOT NULL,
  result TEXT,
  status TEXT DEFAULT 'pending',
  success INTEGER DEFAULT 0,
  count INTEGER DEFAULT 0,
  source_url TEXT,
  source_urls TEXT,
  http_status INTEGER,
  raw_excerpt TEXT,
  error TEXT,
  duration_ms INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_queries_job ON queries(job_id);
CREATE INDEX IF NOT EXISTS idx_queries_case ON queries(case_file_id);
CREATE INDEX IF NOT EXISTS idx_queries_source ON queries(source_id);
CREATE INDEX IF NOT EXISTS idx_queries_status ON queries(status);

CREATE TABLE IF NOT EXISTS case_files (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  question TEXT NOT NULL,
  entity TEXT,
  plan TEXT,
  evidence TEXT NOT NULL,
  missing TEXT NOT NULL,
  confidence TEXT NOT NULL,
  answer TEXT,
  sources_queried TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT DEFAULT 'pending',
  result TEXT,
  error TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  key_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'reader',
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT (datetime('now')),
  last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  api_key_id TEXT,
  question TEXT NOT NULL,
  entity TEXT,
  sources_queried TEXT,
  confidence TEXT,
  duration_ms INTEGER,
  ip_address TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity);

CREATE TABLE IF NOT EXISTS source_verification_runs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  completed_at TEXT,
  total INTEGER NOT NULL,
  ok INTEGER NOT NULL,
  warning INTEGER NOT NULL,
  failed INTEGER NOT NULL,
  duration_ms INTEGER,
  report TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_verification_results (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  status TEXT NOT NULL,
  probe_url TEXT,
  http_status INTEGER,
  latency_ms INTEGER,
  detail TEXT,
  error TEXT,
  checked_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES source_verification_runs(id)
);
