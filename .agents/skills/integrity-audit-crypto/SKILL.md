---
name: integrity-audit-crypto
description: Procedures for maintaining, testing, and auditing the tamper-evident cryptographic log and report generation system. Use when modifying worker/audit.py, schema.sql, scripts/verify_audit.py, worker/report.py, Ed25519 signature checks, hash-chained events, or PDF export generation.
---

# Integrity Audit & Cryptography Skill

## Overview

This skill covers the cryptographic integrity ledger, event signing, hash chaining, and verifiable PDF export generation in Interview Integrity Monitor. The system guarantees non-repudiation and detects log alteration while maintaining candidate consent.

## When to Use

- Updating or inspecting the SQLite audit schema in [`schema.sql`](file:///c:/Users/aravi/projects/interview-integrity-monitor/schema.sql) or event append logic in [`worker/audit.py`](file:///c:/Users/aravi/projects/interview-integrity-monitor/worker/audit.py).
- Working with Ed25519 signature checkpoints and key generation (`cryptography.hazmat.primitives.asymmetric.ed25519`).
- Modifying or running the offline verification script in [`scripts/verify_audit.py`](file:///c:/Users/aravi/projects/interview-integrity-monitor/scripts/verify_audit.py).
- Enhancing PDF audit reports in [`worker/report.py`](file:///c:/Users/aravi/projects/interview-integrity-monitor/worker/report.py) using ReportLab.

## Core Security Requirements

1. **Hash Chain Invariant**:
   - Every event in the audit log must contain a SHA-256 hash calculated as:
     `current_hash = SHA256(prev_hash || timestamp || event_type || payload_json)`
   - The genesis event must chain to a known initial root hash (`0000000000000000000000000000000000000000000000000000000000000000`).

2. **Explicit Candidate Consent Prior to Event Logging**:
   - No monitoring event may be appended to the ledger before a signed consent event is registered.
   - The session scope and disclosures must be captured as part of the immutable session header.

3. **Checkpoint Signatures**:
   - Periodic checkpoints (and session termination) must be signed with the local Ed25519 private key.
   - Public keys must be included in exported bundles to allow third-party offline verification.

4. **Offline Verifiability**:
   - Audits must remain verifiable offline without contacting remote servers.
   - The verification script must validate both the chain continuity and Ed25519 signatures.

## Verification Commands

```powershell
# Run audit and crypto unit tests
python -m unittest tests/test_audit.py -v

# Verify an existing exported audit package
python scripts/verify_audit.py output/sample-audit.json
```
