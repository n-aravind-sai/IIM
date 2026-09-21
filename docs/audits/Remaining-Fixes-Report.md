# IIM — Remaining findings: fixes and audit

Reviewed: 21 September 2026. Repository: `n-aravind-sai/IIM`, branch `audit/remediation`.

## Outcome

All remaining findings have code changes and individual audit records. F08's full Chromium flow passed in GitHub Actions run 35586661249. Native CI exposed test portability issues, corrected below; the rerun passed on Windows and macOS. These changes do not constitute approval for real-interview use.

| Finding | Change | Focused verification |
|---|---|---|
| F04 — incompatible extension checksums | Versioned Unicode-safe canonical format shared by companion exports and worker; explicit consistency-only labels | 6 tests passed, including actual JavaScript exports imported by Python |
| F05 — inconsistent privacy disclosures | Version 2 consent covers retained camera metadata; UI/docs/PDF distinguish optional microphone preview from recording | 3 disclosure tests and 10 device-lifecycle tests passed |
| F06 — inaccurate/misleading summaries | Local deterministic default, actual scope counts, effective provider threshold, no displayed compliance score | 8 summary tests passed |
| F07 — indefinite camera startup | 10-second first-measurement deadline and 3-second stale-data limit, evaluated at camera polls; terminal cleanup and unknown coverage while waiting | 7 timeout/error/cleanup tests passed |
| F10 — request-dependent expiry | Startup and periodic idle cleanup; independent read-time expiry enforcement | 5 tests passed, including idle deletion without HTTP traffic |
| F08 — stale browser assertion | Stable detector/status attributes, explicit process-only test scopes and Linux Chromium CI job | Full Chromium flow passed in CI run 35586661249 |
| F09 — stale source hashes | Regenerated manifest for current tracked source, LF checkout normalization, checksum check in CI | Local manifest verification passed |

Each finding's detailed scope, evidence and limits is recorded in its `Fxx-*.md` audit file in this directory. Prior F01–F03 fixes remain in the regression suite and were published in import commit `40420cb84259ac9020641a6db20ba65623e8590c`.

## Integrated checks

- 94 Python tests passed, including signature/tampering, consent, API, report generation, subprocess shutdown, import compatibility and idle cloud expiry.
- 10 JavaScript pre-flight lifecycle tests passed using actual production handlers and mocked devices/DOM.
- Static UI build, JavaScript syntax and whitespace checks passed.
- Actual PDF-generation and transient-evidence extraction tests passed within the Python suite.
- The browser command was attempted and failed before any page interaction because Chromium is absent. No local browser pass is claimed. The new CI job installs Chromium and exercises consent, demo, note escaping, stop/delete, native process-only session, exports and mobile layout.

Local environment: Linux, Python 3.12.14, websockets 16.0, cryptography 46.0.0, ReportLab 4.4.9. The pinned websockets 15.0.1 could not be installed from this environment's package source during the preceding audit. CI installed the exact requirements successfully on Linux, Windows and macOS. The Chromium flow and macOS Python suite passed.

## Compatibility and limitations

- New sessions require `iim-consent-2`; v1 consent is rejected. Historical exports remain readable and display their recorded disclosure version.
- New companion exports use `iim.extensions.v2`. Legacy Python-compatible v1 digests and unsigned lists remain supported. Older companion files affected by the original locale/Unicode bug need re-exporting. Checksums do not attest browser identity or completeness.
- `PromptLoopConfig.strict_compliance` was removed because its apparent ability to relax validation was unsupported. Supplying it now raises an explicit argument error. The local summary makes no external calls; internal evaluator scores are text checks, not compliance certification.
- Camera deadlines include polling/scheduling delay. Retry requires a fresh consented session, preventing silent reopening after failure.
- Cloud rows expire after 24 hours and are swept within the 60-second maintenance interval plus normal server-loop delay while running. Stopped servers clean at next startup. Backups, exports and filesystem snapshots require independent retention.
- Bundled sample artifacts and the baseline audit are historical examples. Generate a current synthetic report with `python scripts/sample_report.py`; never use an old example as proof of current validation.

Still outstanding: Windows/macOS native permissions and physical-device release, installer verification, dependency/supply-chain review and separately measured detection accuracy. This audit cannot establish legal compliance or suitability for hiring decisions.

## Native CI follow-up

Run 35586661249 found Windows-only test defects: source files and Node output were decoded with the system code page, and test SQLite connections were committed but not closed. Tests now explicitly use UTF-8 and close connections after each helper operation. No assertions were removed. Matrix fail-fast is disabled so one platform cannot cancel the other platform’s verification. macOS passed Python tests, manifest verification, JavaScript lifecycle tests and the UI build before its Rust check was cancelled by the Windows failure. The fresh run passed both native source-check jobs and the Chromium job.

## Verified published revision

[GitHub Actions run 35587169271](https://github.com/n-aravind-sai/IIM/actions/runs/35587169271) passed all three jobs for commit `fc874cfd87d8d9530db40764582b5ee8e22a9911`: Windows source verification, macOS source verification and Linux/Chromium. Both native jobs passed the Python suite (Windows: all 94 passed; macOS: 93 passed, one Poppler-dependent extraction test skipped), all 10 JavaScript lifecycle tests, source checksums, UI build and Rust `cargo check`. The PDF extraction test also passed in the local 94-test run. Python requirements were installed at their pinned versions in CI.

This final documentation update changes the audit and its source-manifest hashes only; the executable source is identical to the verified revision. Compilation does not verify installers, OS permissions, camera hardware or detection accuracy.
