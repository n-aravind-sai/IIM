# Interview Integrity Monitor — prioritized work plan

Prepared: 22 September 2026.

This backlog consolidates the supplied scenario assessment, the local implementation, the existing audit records, and the preceding review. Priorities reflect correctness, candidate control, usefulness of evidence, and dependencies before expanding detection.

Implementation has started. See [foundation progress and validation](foundation-progress.md) for delivered changes and remaining work per P0 item. The tables below retain the complete acceptance targets; a partially implemented item is not marked complete.

The [9 October audit-branch review](audits/2026-10-09-branch-consolidation.md) preserves the older focus/device-count prototypes in Git history and records porting checks for P1-02, P1-04 and P0-06. These prototypes are not enabled on main.

Review follow-ups are tracked in the progress document. By 28 September, metadata-preserving interpretation, explicit unverified policy approval, session-bound expiring inventories, stale-measurement gaps, Windows desktop-count comparisons, camera measurement-quality checks and a consented current-session RDP protocol collector are implemented. Browser/editor integrations, physical topology, third-party remote/audio attribution and the broader release gates remain open. On 29 September, supported Windows process/window source grouping and overlapping-deduction handling were added to P0-07. General episode duration and browser/audio attribution remain open. See the progress document for exact boundaries; the tables retain full acceptance targets.

## Priority and scope

| Priority | Meaning |
|---|---|
| P0 | Foundation work: resolve before relying on reports in real interviews or adding behavior-based alerts. |
| P1 | First dependable release: implement the agreed core checks and complete the applicable release gates. |
| P2 | Optional capability expansion: proceed only after the foundations and an evaluation of usefulness, privacy, and platform feasibility. |
| Deferred | Unsupported claims or proposals that need redesign rather than a detector added to the backlog. |

P1 packaging and validation remain release requirements even though they follow P0 implementation. Optional features can be omitted from a release if their absence is explicit. Cloud work is required only if remote reporting will be deployed. Dates and effort estimates should follow the P0 baseline and platform feasibility work; they are not established by this review.

## Baseline: preserve completed work

The current code contains fixes for the earlier F01–F10 findings. The [latest audit](audits/Remaining-Fixes-Report.md) records their historical CI verification; that record was read locally, not independently rechecked against GitHub in this planning pass.

| Existing capability | Remaining obligation |
|---|---|
| F01: cancelled preflight requests and device cleanup | Preserve lifecycle tests; verify real permission dialogs and devices. |
| F02: killable probes, independent watchdog, late-result guards | Preserve these protections; fix the separate overlapping-stop failure in P0-02. |
| F03: full signed transient observations and resolution events | Preserve evidence-before-publication and JSON/PDF regression tests. |
| F04: Unicode-safe companion checksums | Preserve interoperability; add freshness and scope metadata in P1-05. |
| F05: versioned consent and aligned preview/camera disclosures | Extend disclosure for each new scope before enabling collection. |
| F06: accurate deterministic summaries | Extend summaries to policies, gaps and episodes without inventing conclusions. |
| F07: camera startup and stale-result deadlines | Preserve deadlines; distinguish measurement delivery from actual frame freshness. |
| F08: stable browser assertions and browser CI | Rerun against the eventual release artifact and new workflows. |
| F09: refreshed source manifest | Regenerate from final release contents; include new files. |
| F10: startup/idle cloud expiry and read-time expiry checks | Preserve tests; add deployment operations only if cloud is used. |

Direct process-name matching, Windows binary-metadata matching, sampled overlay transitions, multiple-face observations, lighting checks, camera subprocess isolation and data minimization already exist. These need calibration, broader tests or targeted extensions, not wholesale reimplementation.

The preceding local review passed the static UI build, JavaScript syntax checks, 10 JavaScript lifecycle tests, 97 listed source checksums and sample-audit internal verification. The Python run produced 78 passes, 2 failures and 4 errors across 84 discovered entries; ReportLab was absent, so some test modules did not load. Python 3.14 and installed dependency versions differ from the project target. Windows key protection passed outside the restricted execution environment. These results do not replace a clean, exact-dependency test run or the historical audit's results.

## P0 — foundations

| ID | Work to complete | Completion criteria | Dependencies / main areas |
|---|---|---|---|
| P0-01 | Establish a reproducible baseline. Prepare an isolated Python 3.12 environment with declared dependencies, including ReportLab. Run the complete Python, JavaScript and browser suites; capture versions and test counts. | Every test module loads; each failure is reproduced and classified. Core exports and QR generation run. Record any genuine platform skips separately. Do not count restricted-environment DPAPI failures as product defects. | First; `requirements*.txt`, `tests/`, CI. |
| P0-02 | Fix overlapping shutdown. Coordinate stop requests from the UI, disconnect handler, watchdog and application exit; repeated requests must join or safely observe cleanup. Preserve explicit failed-cleanup state. | Concurrent stops complete without the observed uncaught “Device cleanup is still in progress” error; one terminal session transition; all children reaped; storage closed. Test stop during scans, disconnect/exit overlap and cleanup failure. | P0-01; `worker/engine.py`, `worker/server.py`, Rust lifecycle. |
| P0-03 | Define a versioned event contract for new telemetry. Add producer event IDs, session/run identity, sequence/replay handling, monotonic duration measurement and wall-clock display timestamps. Retain the existing audit chain. | Duplicate/retried events do not inflate counts or durations; reordered and missing events are explicit; old-session events cannot enter a replacement session; clock changes do not create negative durations. Existing exports remain readable or have a tested migration. | P0-01; engine, audit, schema, RPC/client. |
| P0-04 | Represent coverage gaps explicitly. Track per-detector unavailable intervals and whole-session interruption for process death, UI loss, revoked permissions, sleep/resume, stale data and storage failure. | Dashboard and exports show affected scope, reason, last reliable observation and recovery/stop boundary. Abrupt death is marked retrospectively with uncertainty; never fabricate exact outage times or continuity across reboot. Restart still requires fresh consent where applicable. | P0-02, P0-03; engine, shell, detector statuses, report. |
| P0-05 | Add a candidate-visible session policy. Define allowed applications, permitted displays, interview phases, approved collaboration and agreed accommodations. Record policy version and changes in the audit. | Switching to an approved IDE, meeting app, documentation or accessibility tool is handled according to the agreed phase. No silent expansion of monitoring. Policy exceptions can be explained in the report without collecting medical details. | P0-03; policy model, consent UI, engine and report. |
| P0-06 | Correct audio classification and scoring. Separate ordinary hardware loopback, virtual routing, unknown devices and observed activity. Make benign Stereo Mix inventory zero-weight; configurable rules must not equate availability with use. | Stereo Mix alone causes no index deduction; Bluetooth headphones alone cause no adverse signal; routing inventory is accurately labelled. Test benign, virtual, ambiguous and denied-access cases. Expanded names are reviewed fixtures, not blanket substring accusations. | P0-01, policy integration from P0-05; audio detector, rules, scoring. |
| P0-07 | Correlate related observations into review episodes and review cross-detector scoring. Define rules using supported evidence and time relationships; do not assume contemporaneous signals share a source. | One known tool producing process/overlay/audio/extension signals is not counted as four independent incidents. Original evidence remains available. Unknown associations remain separate or explicitly uncertain. Gaze, face count, coverage gaps and permitted activity remain outside adverse scoring. | P0-03, P0-05, P0-06; engine/models, dashboard and report. |
| P0-08 | Align capability claims, data disclosures and trust labels. Publish a platform-specific supported/partial/unsupported matrix. Distinguish content checksum, signed audit integrity, software provenance and live observation authenticity. | README, dashboard, report, security/deployment docs and current verification record agree. External devices and embedded AI limits are explicit now. New scopes have versioned consent and data/retention definitions. Old audit records remain labelled historical. No “all hidden overlays” or “tamper-proof client” claim. | Starts immediately; finalized against P0-04–07 and release tests. |

P0 exit: a reproducible regression baseline; reliable cleanup; durable, ordered evidence and explicit gaps; policy-aware interpretation; corrected audio behavior; reviewable correlated observations; accurate disclosures.

## P1 — core scenarios and first dependable release

| ID | Work to complete | Completion criteria | Dependencies / main areas |
|---|---|---|---|
| P1-01 | Add foreground-application departure/restoration observations on supported OS APIs. Compare minimized application identity with the current phase policy. | Record departure, return and measured duration. Approved IDE/meeting/accessibility switches are legitimate-use negatives. Permission failures produce unknown coverage; no window titles collected by default. | P0-03–05, P0-08; native probes, detector, UI/report. |
| P1-02 | Add consented browser visibility/focus and fullscreen observations on a controlled interview surface. Define which page is actually observed. | Record tab/page departure, restoration and away duration with deduplication. Test permission dialogs, minimized windows, fullscreen exit and reconnect. Dashboard visibility alone is never presented as visibility of the interview tab or all browser activity. | P0-03–05, P0-08; web client or explicit interview integration. |
| P1-03 | Validate display topology and enforce an agreed maximum. Distinguish adapters from active monitors and mirrored/extended configurations; keep virtual classification platform-specific. | Single monitor, multiple monitors, docks, mirrored displays, virtual adapters and hot-plug fixtures yield correct counts or explicit uncertainty. Allowed maximum is policy-driven. macOS does not inherit unsupported Windows classifications. | P0-05, P0-08; native display APIs, detector, report. |
| P1-04 | Monitor device changes after preflight. Add camera/audio/display connect, disconnect and default-device-change events using available APIs and a documented polling fallback. | Changes are timestamped, scoped by consent and reflected in coverage. Disconnect/reconnect and permission revocation work during sessions. Replacement hardware is not silently opened without the required consent/retry flow. | P0-03–05; native/gaze, browser preview, engine. |
| P1-05 | Preserve browser-inventory freshness and scope. Carry export/import times, declared browser/profile scope, session binding and format version through validation, storage and reports. Add freshness policy and stronger configurable extension rules. | Stale, future-dated, wrong-session and multi-profile submissions are explicit. Candidate-supplied times/scope remain untrusted claims. Unicode compatibility survives. A matching digest is still labelled consistency only. | P0-03, P0-05, P0-08; companion, inventory validator, engine/report. |
| P1-06 | Harden and validate existing process/overlay rules. Test executable names, missing/changed version metadata, product descriptions, overlays and capture-affinity failures. Version rule sets and record the version used. | Legitimate captions, recording tools and accommodations have negative fixtures; renamed-process tests cover Windows behavior and missing metadata. Unknown affinity stays unknown. No paths/arguments or unmatched inventories leak into persistent evidence. | P0-05, P0-07–08; native, detectors, rules. |
| P1-07 | Measure sampling blind spots and add OS notifications where justified. Benchmark short process/window events before changing scan intervals or collector architecture. | Publish observed detection rates by event duration, delivery latency and resource cost. Event subscriptions and fallback polling have cleanup/permission tests. Do not describe polling or hooks as comprehensive capture. | P0-02–04, P1-06; probes/native, performance harness. |
| P1-08 | Distinguish observable active remote sessions from installed remote-support tools. Conduct Windows/macOS feasibility checks and implement only the supported evidence. | Installed-but-idle software does not imply active control. Approved support/collaboration is covered by policy; unsupported attribution remains unknown. Do not claim hidden third-party remote access is comprehensively detected. | P0-05, P0-08, P1-06; native collectors and policy. |
| P1-09 | Add basic camera health observations: no face, capture read failure, low quality, stale frame delivery and possible frozen-frame indicators. Keep replay/liveness inference separate. | Simulated disconnects, black frames, stale delivery and a genuinely still participant are distinguishable where evidence permits. Store minimized health metrics, no frames. Virtual-camera names and repeated images do not establish substitution. | P0-03–04, P0-08; camera subprocess and report. |
| P1-10 | Build policy/episode/gap review UX. Show durations, contributing evidence, uncertain associations, candidate explanations and platform limitations consistently in dashboard, signed JSON and PDF. | A reviewer can reconstruct a session without the live dashboard. Candidate explanations persist with the evidence. Keyboard/screen-reader use and mobile layouts pass; new strings and user input remain escaped. | P0-04–08; integrate P1 features as delivered. |
| P1-11 | Package a reproducible standalone desktop build. Choose and bundle a relocatable Python runtime and native dependencies; align staging paths, Rust lookup and Tauri resources. Lock npm/Cargo and reviewed Python dependency sets. | Clean target machines can install, launch, monitor permitted scopes, export, stop and uninstall without developer Python. Build contents exclude local state, keys, test databases and virtual environments copied by accident. | P0-01–02; Rust/Tauri, sidecar scripts, CI and dependency review. |
| P1-12 | Validate and sign release artifacts on Windows/macOS. Exercise physical devices, WebView permissions, interpreter permission attribution, crash/forced exit, sleep/resume and meeting-app contention. Add signing/notarization and final manifest generation. | Exact built artifacts pass the acceptance matrix on supported OS/architecture combinations; physical devices release correctly; publisher verification succeeds; new files are included in release checksums. Rust source compilation alone is insufficient. | P1-11 plus selected P1 capabilities. |
| P1-13 | Establish effectiveness and performance evidence. Define representative legitimate-use and positive scenarios, ground truth, false positives/missed observations, latency, CPU/RAM, battery and a two-hour soak. | Predeclared acceptance thresholds are evaluated by scenario/platform; report uncertainty and dataset limits. CI correctness and heuristic confidence are not advertised as validated detection accuracy. No automated candidate ranking or rejection. | Design begins during P0; results required for the released feature set. |
| P1-14 | Productionize optional cloud reporting if selected: managed identity, scoped per-report access, TLS deployment, token rotation, resource limits, operations and backup/export retention. | Unauthorized cross-report access is denied; upload requires approval and pinned source identity; idle expiry survives operations tests. Docker/deployment and restore tests pass. Preserve single-tenant isolation unless multi-tenancy is explicitly implemented. | Conditional on cloud deployment; P0-08 and release/retention tests. |

P1 exit: the selected feature set works on the supported platforms with clear evidence limits, a usable report, measured behavior and verified installable artifacts. Unselected optional features remain visibly unavailable.

## P2 — optional expansion after the baseline is dependable

| ID | Work / decision | Completion criteria | Dependencies |
|---|---|---|---|
| P2-01 | Observe answer-input provenance in an editor/interview surface the product controls: paste, drop, file import, completion and supported collaborative edits. | Retain event type/size/timing only by default, not clipboard/text contents. Reading back a solution, permitted paste, dictation and accessibility input have legitimate-use tests. No fixed 80-character threshold treated as proof. If there is no owned/integrated surface, mark unavailable. | P0-03–05, P0-08; requires an editor/provider integration. |
| P2-02 | Explore embedded AI visibility through supported editor/browser/meeting integrations. | Produce a per-provider feasibility matrix. Clearly separate installed capability, enabled configuration and observable use. Unsupported integrations remain unknown; process presence cannot close this gap. | P0-05, P0-08; explicit integrations and consent. |
| P2-03 | Consider a consented native-messaging companion for live inventory refresh and session challenges. Evaluate explicit per-profile enrollment before any automatic profile scan. | Disconnects, stale replies and wrong-session submissions are visible. Candidate sees profiles covered and permissions requested. A nonce/heartbeat is not labelled proof of an unmodified browser or complete inventory. No hidden history/profile crawling. | P1-05; additional extension/desktop integration and threat model. |
| P2-04 | Evaluate limited window-title matching only if application identity is demonstrably insufficient. This changes the current no-window-text model. | Separate scope and disclosure, local matching, minimized retained output and tests for confidential titles. It must improve measured usefulness enough to justify collection. A search/AI title alone does not establish use or misconduct. | P1-01, P1-06, P1-13; privacy/design decision. |
| P2-05 | Evaluate better gaze/head-pose algorithms and camera substitution/replay indicators as separate experiments. | Compare against the current proxy across cameras, lighting, glasses, skin tones and normal movement. Keep zero scoring weight unless separately justified through product review and evidence. No face recognition or identity-continuity claim is implied. | P1-09, P1-13; hardware evaluation and updated consent. |
| P2-06 | Evaluate optional local speech-duration/VAD, transcription or phrase analysis as separate scopes. Redesign question-reading and “AI-prompt” rules first. | Verify whether processing is local; no undeclared network audio transfer or saved audio/transcripts. Test interviewer speech, thinking aloud, noise and accommodations. VAD cannot establish speaker identity or meaning. Phrase matches cannot determine assistance. | P0-05, P0-08, P1-13; explicit audio architecture decision. |
| P2-07 | Add interviewer-led understanding checks and structured context: explain a design decision, adapt a constraint or debug a variation. | Record the prompt/context and reviewer notes only with the agreed workflow and retention. No automatic inference of misconduct from a weak answer. Can be piloted as a documented workflow before building new UI. | P0-05, P1-10; interviewer workflow scope. |
| P2-08 | Evaluate stronger provenance and external checkpoints if the threat model needs them. Consider independent session checkpoint anchoring, platform key storage and managed-device attestations where available. | State exactly which rollback, key-theft or provenance threat each control addresses. Test key recovery/rotation and checkpoint mismatch. None is sold as proof that an owner-controlled client reported truthful or complete observations. | P0-08, P1-11–12; external service/managed-device decisions. |

## Proposals to redesign or keep as coverage limits

These are accounted for in the plan, but are not requirements to implement as adverse detectors.

| Proposal | Disposition |
|---|---|
| Block shortcuts to guarantee a secure browser | Defer any kiosk product as a separate managed-environment project. Document shortcut and OS limitations now; do not promise browser lockdown from page handlers. |
| Infer attention or assistance from mouse leaving the viewport | Exclude from adverse scoring. Prefer explicitly scoped visibility observations; permission dialogs and ordinary workflow are legitimate causes. |
| Detect a covert earpiece from Bluetooth/device inventory | Inventory can describe observable devices under consent; it cannot determine what someone hears. No cheating flag from headphones. |
| Treat reading questions aloud, sustained speech or a phrase match as AI use | Redesign as optional contextual observations, if validated, under P2-06. |
| Guarantee detection of phones, tablets, printed notes or off-camera helpers | Disclose as coverage limits under P0-08. Optional in-frame object research would need its own requirements/evaluation; off-camera absence cannot be established. |
| Guarantee detection of external capture hardware, independent audio help or every hidden overlay | Disclose the limits under P0-08; platform metadata cannot support those guarantees. |
| Authenticate browser truthfulness through an editable checksum or challenge response | Preserve consistency checks and session binding, while making the stronger unsupported claim explicit. |
| Interpret the technical index as misconduct probability or a pass/fail decision | Keep prohibited in product behavior and reporting. Episode correlation improves evidence organization, not statistical validity. |

## Delivery sequence and dependency boundaries

1. **Baseline and lifecycle:** P0-01, P0-02; begin P0-08 documentation immediately. Preserve all existing F01–F10 regressions.
2. **Evidence and policy:** P0-03, P0-04, P0-05. These contracts precede new event sources. Draft the evaluation scenarios from P1-13 here.
3. **Interpretation:** P0-06, P0-07 and the first P1-10 report/UI changes. Complete the P0 disclosure alignment.
4. **Core observations:** P1-01–06 and P1-09. Device/display work and inventory work can proceed independently once the contracts are stable.
5. **Measured extensions:** P1-07–08 where feasible. Packaging P1-11 can proceed alongside core feature work after the environment and shutdown baseline is stable.
6. **Release gate:** complete P1-10, P1-12–13 and P1-14 if cloud is selected. Run validation on the final artifact, not an earlier development checkout.
7. **Optional work:** select P2 items based on measured value. P2-07 can start earlier as an interviewer workflow; speech/gaze experiments must not block a release that explicitly excludes them.

The first implementation batch should therefore be the clean dependency/test baseline and a focused overlapping-shutdown regression/fix, followed by the event/gap contract and session-policy model.

## Definition of done for each capability

Every implemented observation needs a positive fixture, a legitimate-use negative fixture, a permission/unavailable case, and a supported-platform test. Mark unsupported platforms explicitly. Add duration/retry/order and stop/restart tests where the capability produces events or owns resources.

Each completed item must also demonstrate scope-gated collection, minimized retention, matching dashboard/JSON/PDF behavior, rule/policy version attribution where applicable, and an honest limitations label. Changes to collected data require updated consent before activation. Physical-device claims require physical-device evidence; mocked tests remain labelled as such.

Shared release checks cover signed-evidence tampering, old-export compatibility, database failure, deletion/expiry, absent dependencies, inaccessible devices, browser/WebView differences, packaging without developer tools, and long-running resource use. Record exact versions, artifact identity, pass/fail/skip counts and unresolved limitations.

## Implementation map

| Area | Primary files |
|---|---|
| Lifecycle, events, policy, gaps | `worker/engine.py`, `worker/server.py`, `worker/models.py`, `worker/audit.py`, `schema.sql` |
| Native observations and rules | `worker/native.py`, `worker/probes.py`, `worker/detectors.py`, `worker/rules.json` |
| Camera health and experiments | `worker/gaze.py`, `tests/test_camera_timeout.py`, `tests/test_shutdown.py` |
| Browser inventory | `companion/`, `worker/inventory.py`, `tests/test_inventory.py` |
| Consent, review and browser events | `web/index.html`, `web/app.js`, `web/style.css`, `tests/preflight.mjs`, `tests/browser.mjs` |
| Evidence and reports | `worker/report.py`, `worker/prompt_loop.py`, `tests/test_evidence.py`, `tests/test_cloud_report.py` |
| Desktop and release | `src-tauri/`, `scripts/prepare_sidecar.py`, `scripts/source_manifest.py`, `.github/workflows/`, dependency manifests |
| Optional cloud | `cloud/`, `scripts/upload_report.py`, `Dockerfile`, `compose.yaml`, `tests/test_retention.py` |

The wider keyword/device lists referenced by the supplied assessment were not included in the pasted text. Exact additions belong in a reviewed rule specification under P0-06/P1-05/P1-06; this plan does not invent those missing lists.
