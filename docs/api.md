# Backend API design

## Local WebSocket API

Endpoint: ephemeral `ws://127.0.0.1:<port>`, returned by the native `bootstrap` command. Tokens travel over private parent pipes and local IPC, never query strings. Production origins: `tauri://localhost`, `http://tauri.localhost`, `https://tauri.localhost`. Development adds only `http://127.0.0.1:1420` and `http://localhost:1420`. Missing and unrelated origins are denied.

Authenticate within five seconds with `{"token":"<capability token>"}`. The response is `{"type":"ready","snapshot":{...}}`. The token is per worker, 32+ characters, and is not an identity credential or proof of device trust. One authenticated controller is allowed.

Requests have `{"id":"client-request-id","op":"start","args":{...}}`. IDs are strings up to 80 characters; incoming messages are capped at 64 KB. Results have `{"type":"response","id":"...","result":...}` or `{"type":"response","id":"...","error":"..."}`. Server snapshots use `{"type":"snapshot","snapshot":...}`. A fatal error is explicit and stops monitoring.

| Operation | Arguments | Result / rule |
|---|---|---|
| `snapshot` | `{}` | Latest state; before consent contains no observations |
| `start` | `{consent:{accepted:true,version:"iim-consent-2",processes:true,windows:true,displays:true,audio_devices:false,extensions:false,gaze:false}}` | Starts a fresh session; at least one selected scope |
| `heartbeat` | `{}` | Extends active controller lease; UI sends every 4 seconds |
| `stop` | `{}` | Closes optional camera, saves final state, ends session |
| `note` | `{text:"..."}` | Active session only, 1-500 characters; stored and escaped in UI/PDF |
| `mark` | `{kind:"question_end"}` or `{kind:"answer_start"}` | Manual interval; valid order required; no score impact |
| `extensions` | `{entries:[{name:"...",enabled:true}]}` | Active session plus extension consent; max 250 entries, names truncated to 100 characters |
| `export_json` | `{}` | Complete signed audit bundle, verified against stored seal |
| `export_pdf` | `{}` | `{filename,base64}` generated from a verified audit bundle |
| `delete` | `{}` | Inactive current session only; cascades events and seal |

No generic shell, filesystem read, process execution, remote monitor start, screenshot upload or camera-frame API is exposed.

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

Retention is 24 hours. Expired records are inaccessible and pruned on the next API operation. Configure periodic cleanup, encrypted backups and deletion propagation before production. TLS termination, OIDC, role lifecycle, tenant isolation, load limits and operational audit trails are deployment responsibilities, not implemented SaaS features.

### Future live interviewer relay

Use separate candidate and interviewer identities, short-lived pairing invitations, explicit candidate approval, read-only interviewer tokens, revocation and server-attested receipt times. Transmit only minimized observations, capability states and candidate context. Preserve connectivity gaps in reports. Do not expose the current loopback worker or reuse its capability token on a public network. No live relay is implemented or deployed here.
