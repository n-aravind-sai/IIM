PRAGMA secure_delete = ON;
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  bundle_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS report_expiry ON reports(expires_at);
