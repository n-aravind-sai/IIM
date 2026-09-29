# Backend API design

## Local WebSocket API

Endpoint: ephemeral `ws://127.0.0.1:<port>`, returned by the native `bootstrap` command. Tokens travel over private parent pipes and local IPC, never query strings. Production origins: `tauri://localhost`, `http://tauri.localhost`, `https://tauri.localhost`. Development adds only `http://127.0.0.1:1420` and `http://localhost:1420`. Missing and unrelated origins are denied.

Authenticate within five seconds with `{"token":"<capability token>"}`. The response is `{"type":"ready","snapshot":{...}}`. The token is per worker, 32+ characters, and is not an identity credential or proof of device trust. One authenticated controller is allowed.

Requests have `{"id":"client-request-id","op":"start","args":{...}}`. IDs are strings up to 80 characters; incoming messages are capped at 64 KB. Results have `{"type":"response","id":"...","result":...}` or `{"type":"response","id":"...","error":"..."}`. Server snapshots use `{"type":"snapshot","snapshot":...}`. A fatal error is explicit and stops monitoring.

| Operation | Arguments | Result / rule |
|---|---|---|
| `snapshot` | `{}` | Latest state; before consent contains no observations |
| `start` | `{consent:{accepted:true,version:"iim-consent-4",processes:true,windows:true,displays:true,audio_devices:false,extensions:false,gaze:false,remote_sessions:false}}` | Starts a fresh session; at least one selected scope |
| `heartbeat` | `{}` | Extends active controller lease; UI sends every 4 seconds |
| `stop` | `{}` | Closes optional camera, saves final state, ends session |
| `note` | `{text:"..."}` | Active session only, 1-500 characters; stored and escaped in UI/PDF |
| `mark` | `{kind:"question_end"}` or `{kind:"answer_start"}` | Manual interval; valid order required; no score impact |
| `extensions` | `{entries:[{name:"...",enabled:true}]}` | Active session plus extension consent; max 250 entries, names truncated to 100 characters |
| `export_json` | `{}` | Complete signed audit bundle, verified against stored seal |
| `export_pdf` | `{}` | `{filename,base64}` generated from a verified audit bundle |
| `delete` | `{}` | Inactive current session only; cascades events and seal |

No generic shell, filesystem read, process execution, remote monitor start, screenshot upload or camera-frame API is exposed.

### Foundation additions

`start` also accepts an optional `policy` object. Omission produces explicit defaults, not inherited permissions. Policy version 1 fields are `phase` (`discussion`, `coding`, `open_book`, `collaboration`), `allowed_apps` (up to 50 exact executable names), `phase_apps` (phase-to-name-list mapping), `max_displays` (null or integer 1–8), and `context` (up to 500 characters). Paths, wildcards, unknown fields and invalid limits are rejected. Names are normalized case-insensitively with an optional `.exe` suffix removed. The display maximum is compared with the Windows OS desktop monitor count when display consent is selected. An excess is a zero-weight review observation. Adapter count is separate; mirrored physical displays remain unknown.

The authenticated `policy` operation requires `{policy, expected_session_id, expected_revision, accepted:true}` during an active session. Both identifiers must come from the session snapshot being edited. The worker validates session identity and revision together under its lock; missing/mismatched session IDs, stale revisions and missing acceptance are rejected without changing the audit. Revisions restart for each session and cannot identify a session on their own. Changes do not expand monitoring consent. Initial rules and each accepted revision are signed as `session_policy` events. All candidate-declared exceptions retain original weights: independent approval is unverified. The server assigns `approval_status:"unverified"` and `source:"candidate"`; clients cannot submit approval fields. Policy annotations in new samples include `interpretation_version:3` and disposition `pending_review` or `identity_review`. Neither executable names nor binary metadata authenticate application identity. PDF policy interpretations are read from recorded samples, including legacy version-1 and version-2 decisions; they are never recalculated using current rules. Policy changes do not rewrite historical events. Candidate-declared agreements are not independently authenticated interviewer instructions.

Snapshots add `review_groups`, `policy`, `policy_revision`, `stopping`, `cleanup_state` (`idle`, `in_progress`, `complete`, `failed`) and `coverage_gaps` (currently open intervals). Simultaneous stop operations join the same cleanup result. Failed cleanup or terminal audit persistence blocks new sessions and deletion; no successful completion is implied.

New audit payloads add `event_version:1`, `event_id` (`session_id:sequence`), `session_id`, `sequence`, `run_id` and `monotonic_ms`. These are covered by the existing hash/signature. The outer `iim.audit.v1` format and legacy verification remain unchanged. Monotonic values are meaningful only within the same run. This does not introduce client event ingestion or make RPC request IDs idempotency keys.

`coverage_gap_opened`, `coverage_gap_updated` and `coverage_gap_closed` events share a gap ID and include scope, detector, status, reason, observed start/end and monotonic duration where available. Unselected scopes do not open gaps. Closing at stop is distinct from measurements resuming. Restart interruption timestamps bound what was observed; exact crash time and outage duration remain unknown.

### Inventory freshness and measurement health

`extensions` accepts legacy arrays/v1/v2 envelopes as unverified history, or a v3 envelope: `{format:"iim.extensions.v3",session_id,exported_at,browser,profile,digest,extensions:[{name,enabled}]}`. V3 requires the active session ID, an aware ISO timestamp younger than 300 seconds (up to 60 seconds future clock tolerance), and browser/profile labels of 1–100 characters without control characters. The digest is SHA-256 of compact ASCII-escaped JSON `[format,session_id,exported_at,browser,profile,v2_entries_digest]`. The existing Unicode-safe v2 entries checksum is unchanged. Claims are not browser authentication: editable content can still be fabricated or incomplete. Only the latest declared profile is represented; imports do not merge profiles.

A signed `extension_inventory_imported` event retains export/import times, scope claims, count, binding and checksum flags before publishing context. Unmatched names remain transient. Freshness expires after five minutes from the claimed export time using a local monotonic deadline; reimporting the same timestamp does not reset that age. Legacy imports cannot close a coverage gap. The browser detector is sampled every ten seconds; the watchdog also invalidates expired usable samples. Native-probe freshness deadlines are 25 seconds, or eight seconds for window/gaze results. Wall-clock or monotonic discontinuities invalidate cached results; exact sleep/outage cause and timing remain unknown. Recovery requires a fresh scan. This is not an OS power-event subscription.

`remote_sessions` is a separate optional scope under disclosure `iim-consent-4`. Windows reads only the worker session's `WTSClientProtocolType` (console/RDP/unknown), without account names, addresses or other sessions. RDP observations have zero weight and do not contribute to the five-detector technical index. Other platforms, failed APIs and third-party remote-control attribution remain unknown.

Camera stream delivery alone is not usable measurement coverage. Uncalibrated, currently unusable or low-quality eye samples remain `waiting`. Transport capture timestamps reject queued stale measurements; this does not authenticate physical-frame freshness or establish liveness.

### Supported process/window source association

Disclosure `iim-consent-4` describes randomized references for related process/window metadata. Only sessions selecting both `processes` and `windows` generate a private, random 32-byte key. It is passed only to those native collectors and discarded at stop. Windows process creation time and PID are used transiently with HMAC-SHA256 to produce `evidence.source:{kind:"windows_process_instance",ref:"<64 lowercase hex>"}`. Neither raw PID, creation time nor the key enters snapshots or audit evidence. Source collection uses limited-query process handles; failed queries never fall back to PID-only identity. Window ownership is checked again after querying the process instance.

`review_groups` contains only usable process/window results sharing that source, with sorted detector/member IDs and `association:"same_os_process_instance"`. It does not infer associations from names, timestamps, browser files, audio devices or unsupported platforms. A `source_groups` event records changed groups immediately, including disappearance between periodic samples. These groups describe sampled OS sources, not continuous activity intervals, software publisher identity or intent.

New scores carry `version:2`. Each detector still contributes only its strongest signal; equal strengths choose the smallest signal ID deterministically. If chosen process/window maxima share a supported source, only the larger deduction is applied. Other detector maxima remain separate; this is not evidence that they describe independent incidents. Raw observations and weights remain unchanged. PDFs preserve recorded legacy scores and only show recorded source associations; historical exports are never retrospectively linked.

### Native IPC

`bootstrap()` starts or reuses the worker and returns `{endpoint,token}`. `save_export({name,bytes})` creates a new file in Downloads, with a unique prefix, constrained JSON/PDF extension and a 16 MB limit. Both commands enforce the main-window label. Review the Tauri command ACL and all navigation paths before production; they are not a substitute for a secure renderer.

## Optional reporting HTTP API

This runs separately from the desktop worker. It is a **single-tenant reference implementation**, not a multi-tenant SaaS. Read and write tokens are distinct, required at startup and scoped to the one configured tenant. Enroll device public keys through `REPORT_TRUSTED_KEYS` via an independently verified channel; never automatically trust a key from the report being uploaded.

| Method and endpoint | Authorization | Behavior |
|---|---|---|
| `POST /v1/reports` | Write bearer token | Body `{consent_to_upload:true,bundle:<signed JSON>}`; validates completed session, enrolled key and chain; returns `201 {id,expires_at}` |
| `GET /v1/reports/{uuid}` | Read or write bearer token | Returns an unexpired audit bundle; no list endpoint |
| `DELETE /v1/reports/{uuid}` | Write bearer token | Deletes the report; idempotent `200 {deleted:true}` |

Errors: `400` invalid payload/consent/audit, `401` wrong credential or insufficient role, `404` unknown/expired report, `429` credential rate limit. Maximum POST size is 8 MB; credential limit is 120 requests/minute. No cross-origin browser API is enabled.

Retention is 24 hours. Every read enforces the expiry timestamp. Expired rows are deleted at startup and at most 60 seconds after expiry while the server loop is running, plus its normal polling/scheduling delay (0.5 seconds by default), without requiring traffic. While stopped, rows remain until the next startup. SQLite secure deletion does not erase exported copies, filesystem snapshots or backups; configure backup retention and deletion propagation separately. TLS termination, OIDC, role lifecycle, tenant isolation, load limits and operational audit trails are deployment responsibilities, not implemented SaaS features.

### Future live interviewer relay

Use separate candidate and interviewer identities, short-lived pairing invitations, explicit candidate approval, read-only interviewer tokens, revocation and server-attested receipt times. Transmit only minimized observations, capability states and candidate context. Preserve connectivity gaps in reports. Do not expose the current loopback worker or reuse its capability token on a public network. No live relay is implemented or deployed here.
