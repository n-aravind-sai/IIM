# F04 — Extension imports

Status: fixed. Six focused tests passed (`test_inventory.py`). Real companion JavaScript exports were imported through the Python engine with accented, mixed-case, emoji, duplicate, long, control-character and lone-surrogate fixtures. Tampering, malformed/missing v2 checksums and unknown versions are rejected. Legacy Python-format digests and explicitly unchecked legacy lists remain supported.

Version 2 retains only names and enabled flags, truncates names to 100 Unicode code points, ASCII-escapes each compact JSON pair, sorts the escaped rows by ASCII bytes and SHA-256 hashes the resulting ASCII array. Sorting includes the enabled flag as a tie-break. The UI forwards the full versioned envelope. Digest matches establish editable-content consistency only: browser identity, authenticity, freshness and completeness remain unverified. Older companion files affected by the original Unicode/locale bug must be re-exported with the current companion.

Native browser-extension installation and management permission were not exercised; the actual shared export module ran in Node and its output was validated by the production engine.
