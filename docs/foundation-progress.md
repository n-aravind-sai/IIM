# Foundation implementation — 23–29 September 2026

This pass implements the first foundation changes from [the prioritized work plan](prioritized-work-plan.md). It does not complete the 30-item roadmap or establish production detection accuracy.

## Source association and overlapping deductions — 29 September

- Added narrow Windows process/window source association under disclosure `iim-consent-4`. Both scopes must be selected. Transient PID plus process creation time produces an HMAC reference using a new private key per session. PID reuse and new sessions produce different references; query failure and unsupported platforms produce no link. Raw IDs, times and key bytes are not retained.
- Window ownership is rechecked after the creation-time query. Process image and creation time come from the same open handle. Native collectors receive only the private key needed for this feature, without browser inventories or other context; limited-query handles are closed on success and failure.
- Index version 2 keeps existing strongest-per-detector caps, but selected process/window maxima from the same supported source contribute only the larger deduction. Names, simultaneous timestamps and candidate-supplied browser claims cannot create a link. Raw observations and confidence/weight fields remain unchanged.
- The dashboard and PDF show recorded source groups. Group changes are signed immediately, preserving short-lived associations between periodic samples. Reports preserve earlier scores and never reinterpret old exports. Groups are sampled source associations, not continuous activity durations or proof of software identity.
- Independent regression tests cover shared/distinct/malformed sources, forged browser linkage, unknown coverage, zero-weight evidence, deterministic ties and unchanged raw data. Additional tests cover key consent/lifetime, PID reuse, minimized evidence, native handle cleanup, child-context filtering and durable brief groups. A local Windows query confirmed matching process-instance creation data for the current Python process; cross-platform and real multi-application acceptance remain release work.

P0-07 is now partially implemented for supported process/window sources. Browser/audio/tool-family attribution, cross-process helpers and continuous review episodes remain open because this implementation has no verified association for them. Separate deductions must not be presented as independent misconduct incidents.

Source: [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) supplies creation time through a limited-query handle; [OpenProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocess) documents access failures and handle ownership.

## Priority hardening — 28 September

Implemented the actionable review weaknesses in priority order, retaining uncertainty where the available APIs cannot support a detection claim:

1. **Policy suppression:** interpretation version 3 marks every candidate rule revision `approval_status: unverified`. Candidate-declared names cannot reduce the index; exceptions remain pending human review. Clients cannot inject approval fields. Metadata matches remain visible at original weight. Historical versions 1/2 are rendered as recorded, without rewriting old evidence.
2. **Inventory scope and age:** companion v3 binds the active session, review/export timestamp, browser/profile labels and entries to one checksum. Invalid scope, inconsistent content, stale timestamps and excessive future dates are rejected before audit/context changes. A locally tracked five-minute deadline expires coverage; legacy files remain explicitly unverified. Concurrent imports cannot publish superseded coverage. The latest declared profile replaces, rather than merges with, previous imports. Claims remain editable and unauthenticated.
3. **Measurement freshness:** the independent watchdog invalidates stale usable results, preserving observations but removing usable coverage. Windows/gaze deadlines are eight seconds; other scopes use 25 seconds. Wall-clock and monotonic age are checked. Fresh scans are required after clock discontinuities; cached results cannot close a gap. Signed boundaries describe detection time, not an invented exact sleep/failure instant.
4. **Display counts:** Windows desktop monitors are counted independently of adapters and compared with the declared maximum. Excess is a zero-weight review observation. Mirrored physical targets, concealed displays and unavailable platform topology remain unknown. macOS display inventory is not mislabelled as Windows adapter inventory.
5. **Camera quality:** a responsive camera with missing calibration, unusable current eyes, low light or insufficient samples remains a coverage gap. Older good aggregates cannot hide an unusable current frame. Capture timestamps prevent delayed pipe messages from appearing freshly measured; transport timestamps are not retained as evidence. Multiple-face observations remain zero-weight. This is not replay/liveness validation.
6. **Remote-session scope:** disclosure `iim-consent-3` adds a separately selectable Windows current-session protocol check. Only console/RDP/unknown is collected, without user names, addresses or other sessions. The collector remains killable and off without consent. RDP observations are zero-weight; console does not establish absence of third-party control.
7. **Review surfaces:** dashboard, consent, companion, signed samples, PDFs and API docs expose approval, freshness, scope and capability limits. Signing/hashing remains compatible with legacy exports.

The browser/editor integration opportunity needs an explicitly integrated interview/provider surface, which this repository does not contain. Per-app audio attribution needs a separate supported OS collector. Neither is claimed implemented through process names or inventory. Off-device assistance, mirrored physical screens, hostile device-owner tampering and replayed camera content cannot be ruled out by this prototype. Broader roadmap items such as general cross-detector episode attribution and physical-device release validation remain open below; the 29 September addition covers only supported process/window sources.

Native sources: [Windows desktop monitor counting](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getsystemmetrics), [current-session query](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/nf-wtsapi32-wtsquerysessioninformationw), and [protocol values](https://learn.microsoft.com/en-us/windows/win32/api/wtsapi32/ne-wtsapi32-wts_info_class). A read-only local check returned one desktop monitor and console protocol; this is one Windows environment, not multi-monitor/RDP hardware validation.

## Enhancement 1 — application identity review, 25 September

- Allowed executable names no longer suppress existing original-filename or product-metadata review matches. These observations retain their original confidence and weight, with an explicit `identity_review` policy annotation. At that time, name-only exceptions continued to work; version 3 now keeps them pending review. No new score penalty or detector is added.
- Conflicting original filenames within the same review-rule group are retained instead of being discarded by the name-match branch. Generic unmatched metadata does not create a new observation. Both names and metadata remain unauthenticated hints; this does not implement publisher/signature validation or prove active assistance.
- New policy annotations carry interpretation version 2. Raw signed observations are unchanged by policy application. PDFs summarize the decisions actually retained in signed samples, including earlier version-1 decisions, without reinterpreting historical exports. Repeated identical decisions are collapsed; these are not continuous-activity intervals.
- Dashboard explanations, rules-editor guidance, consent wording and API documentation describe the metadata exception. Tests cover renamed binaries, same-rule aliases, product metadata, benign exact-name exceptions, phase rules, raw-evidence preservation, signed exports and PDF interpretation history.

The remaining review enhancements proceed in order:

| Order | Enhancement | Status |
|---|---|---|
| 1 | Preserve metadata review matches despite allowed names | Implemented; independent executable authentication remains future work. |
| 2 | Independent policy approval / explicit unverified change state | Explicit unverified state implemented; no self-declared scoring exemptions. Independent approval service remains absent. |
| 3 | Inventory freshness, session and browser/profile scope | Implemented for v3 self-reported files; browser authenticity remains unknown. |
| 4 | Polling gaps and sleep/resume coverage | Stale-age/discontinuity invalidation implemented; exact OS power-event attribution remains absent. |
| 5 | Validated display topology and policy enforcement | Windows desktop counts and declared-limit observations implemented; physical/mirrored topology and enforcement remain unsupported. |
| 6 | Consented browser/editor integrations | Pending feasibility and supported-provider scope. |
| 7 | Separate camera stream health from usable measurement quality | Implemented, including current-frame quality and transport freshness. |
| 8 | Supported active remote/audio attribution | Consented Windows console/RDP protocol implemented. Third-party remote control and active audio attribution remain unknown. |

## Review fixes — 24 September

- Bound each queued monitor poll to its intended session. The engine checks that identity before watchdog actions and again before sampling, so work delayed across a session replacement cannot scan the replacement and misattribute its audit failures. Existing guards still prevent late failures from stopping a healthy replacement. Deterministic regressions cover replacement before dispatch, replacement between watchdog and sampling, and current-session audit failure shutdown.
- Policy updates now require `expected_session_id` as well as `expected_revision`. The worker validates both under the engine lock before writing the audit; the dashboard supplies the identity captured when the rules editor opens. Missing, invalid and previous-session IDs are rejected even when revisions match. API documentation and RPC/UI regression tests cover the new requirement.

Both defects were reproduced by failing regressions before the fixes. These changes do not implement the broader detection enhancements identified in the review.

## Changes delivered

- Created a local Python 3.12.14 virtual environment with the project's exact core pins: websockets 15.0.1, cryptography 46.0.0 and ReportLab 4.4.9. The environment is excluded from source artifacts.
- Concurrent stop requests now share one completion result. Disconnect, watchdog and shutdown cannot independently finalize the same session. Cleanup/audit failures propagate and block restart; deleting a session clears its cached stop result. Background service tasks are joined even when final audit persistence fails.
- Startup is staged. Consent, initial policy and initial coverage records must be durable before monitoring becomes active. Failure releases constructed detectors and preserves the previous completed session. Late errors from an old monitored session cannot stop a replacement session.
- Selected detectors begin with an explicit waiting interval. Signed coverage events record opening, status changes and closing; repeated unchanged failures do not add duplicate intervals. Recovery durations use a monotonic clock. Stopping an interval is distinguished from recovering measurements. The dashboard and PDF show unavailable coverage.
- Signed event payloads now carry a version, stable session/sequence identity, worker-run ID and run-relative monotonic timestamp. Existing audit hashing/signature format and legacy sample verification remain compatible. These are identities for retained worker events, not a general-purpose external event ingestion/retry protocol.
- Restart records include the last persisted event time and an explicitly unknown interruption duration. Open intervals are presented as interrupted, never recovered. Exact crash time cannot be reconstructed from a stopped worker.
- Stereo Mix is an informational hardware-loopback observation with zero index weight. Bluetooth/ordinary microphone names do not create adverse signals. Existing virtual-routing name matches remain labelled as device presence with unknown actual use.
- Added versioned session policies: exact globally permitted executable names, phase-specific names, interview phase, a declared display maximum, and voluntary agreed context. The consent dialog previews the selected rules. Active edits require acceptance and the current revision; every accepted revision is signed.
- Version 3 keeps candidate-declared process exceptions pending review at original weight; matching binary metadata remains for identity review. Raw detector observations remain unchanged in the signed log; samples and live state apply the recorded policy. Phase changes recompute the current interpretation without erasing past evidence or changing monitoring scopes.
- Added explicit stopping/failed-cleanup UI states and corrected the QR description: a checkpoint is not independent proof of device identity, complete monitoring or truthful observations.

## Validation

- Python: **178 tests run; 177 passed, 1 skipped** on 29 September. The existing Poppler-dependent PDF text-extraction test is skipped because `pdftotext` is unavailable on PATH. PDF generation and PDF/QR RPC tests passed.
- JavaScript lifecycle/state tests: **15 passed**, including session identity in policy submissions and escaped source-group rendering.
- Real Chromium: consent, synthetic demo, escaped notes/policy text, policy preparation and live edits, signed policy revisions, process-only session, session-bound v3 extension-only coverage gap/recovery, event identities, stop/delete, JSON/PDF downloads and mobile overflow checks passed without page errors. Test sessions did not enable camera or microphone. The companion popup review/export and permission-failure invalidation also passed with a fixture browser management API; this does not certify installation permissions in Chrome/Edge.
- `pip check` passed. JavaScript syntax and Python compile checks passed. Static UI build, legacy sample-audit internal verification and 113 source checksums passed.
- Policy dialog and mobile screenshots were inspected. This is browser validation, not native Tauri/WebView or physical-device validation.
- The browser workflow, JavaScript syntax check and static desktop UI build passed again after the 24 September fixes.

The regressions first reproduced the overlapping-stop defect, missing coverage/event-contract behavior, Stereo Mix penalty and missing policy behavior. Review additionally identified startup-failure and stale-monitor cleanup defects; dedicated fault-injection/concurrency tests cover them.

## Remaining boundaries

| Plan item | Status after this pass |
|---|---|
| P0-01 baseline | Exact core dependencies and Windows/browser checks established. Clean macOS/native artifact checks remain. |
| P0-02 shutdown | Code fixes and deterministic concurrency tests delivered. Native physical-device release acceptance remains. |
| P0-03 event contract | Signed worker event identity/run clocks delivered. Future external-producer ordering, replay/idempotency and ingestion are not implemented. |
| P0-04 gaps | Detector waiting/failure/recovery, stale-sample deadlines, clock-discontinuity invalidation and retrospective worker interruption delivered. OS sleep/resume notifications, comprehensive permission-revocation events and persistent UI access to previous interrupted sessions remain. |
| P0-05 policy | Candidate-visible/versioned policies delivered. Windows desktop counts are compared with declared limits as zero-weight observations; physical/mirrored counts remain unknown. All exceptions now remain pending independent approval. |
| P0-06 audio | Stereo Mix correction and baseline classification delivered. Wider reviewed device rules and native active-use attribution remain. |
| P0-07 correlation | Shared Windows process/window source groups and overlapping-maxima de-duplication implemented. General tool-family/audio/browser attribution and continuous episode durations remain open. |
| P0-08 claims | Updated API/architecture notes and QR trust wording for these changes. Broader documentation consolidation and final platform capability matrix remain. |
| P1/P2 | Mostly outstanding; small portions of review UX/reporting are included here. No new speech, focus, browser surveillance, liveness or object detection was enabled. |

Policies do not authenticate executables; names can be spoofed. Version 3 does not suppress process penalties on candidate declarations alone. Display excess observations remain review context with unverified approval; they are excluded from the index. Synthetic demo does not implement policy editing.

## Reproduce locally

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/preflight.mjs
npm run build
.\.venv\Scripts\python.exe scripts/verify_audit.py output/sample-audit.json
.\.venv\Scripts\python.exe scripts/dev.py
# In another terminal, with Playwright and Chromium installed:
node tests/browser.mjs
```

The browser script also accepts `PLAYWRIGHT_MODULE` and `CHROMIUM_EXECUTABLE` for an existing installation. This run used the available bundled Playwright package and local Chromium headless shell. Windows DPAPI tests required the ordinary user context rather than the restricted agent sandbox.

Development and validation used an extracted source folder without local Git metadata. The source manifest includes the explicitly added source, test and documentation files; generated environments, local databases and browser screenshots are excluded from GitHub publication.
