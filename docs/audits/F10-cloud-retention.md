# F10 — Cloud retention without traffic

Status: fixed. Five focused tests passed (`test_retention.py`).

The report server deletes expired rows before accepting requests and sweeps from the HTTP server's regular service loop every 60 seconds, independent of HTTP traffic. Every read independently checks the expiry timestamp, so the deletion interval never extends API access. Server shutdown joins bounded-time request handlers before closing SQLite and supports repeated close calls.

Tests verify startup purge, actual idle-server deletion without any HTTP requests, denial of an expired row before its sweep, interval validation and idempotent shutdown. Unexpired rows are retained. Existing authenticated upload/read/delete tests remain part of the full suite.

While running, physical row cleanup is bounded by the sweep interval plus normal polling/scheduling delay (normally 0.5 seconds). A stopped server cannot delete rows; startup removes downtime-expired data. SQLite secure_delete is enabled, but exports, snapshots, external backups, filesystem remnants and failed-storage conditions have separate retention limits. This change does not promise forensic erasure.
