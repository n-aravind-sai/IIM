# Security, privacy and limitations

## Data contract

Only consented metadata and voluntary context enter the session log. The code does not log keys, collect passwords, read browser history, inspect arbitrary documents, capture desktop images, inject code or alter other applications. The session camera runs only with the camera scope selected under disclosure `iim-consent-3`. Its subprocess returns eye-position consistency, quality and calibration statistics, lighting, face count and multiple-face observations; no frames or identity recognition. A separate candidate-triggered pre-flight preview opens camera and microphone in the browser, displays video and microphone level locally, and saves or sends none of that preview data. Closing the check, stopping the session or leaving the page releases its devices. Synthetic demo is hardware-free.

No activity detector starts at login or app startup. Stop remains visible across screens. Worker disconnect and heartbeat expiry end collection. A crash can interrupt cleanup or audit writes; restart records interruption instead of claiming a complete session. Native calls and OS shutdown behavior still require target-device failure tests.

Process names and extension names can disclose personal information. Only matching names are logged. Window PIDs and handles are transient. Device names and candidate notes may still be sensitive. The app uses a pseudonymous random session ID and does not ask for a candidate's name, email or employment profile.

The local database and signing key are **not encrypted by this application**. On Unix their containing directory is restricted to the user; on Windows the app relies on the user's profile ACLs. Prefer OS full-disk encryption, and replace local key-file storage with Keychain/Windows protected storage before production. Exports are separate user files and remain until deleted.

## Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| A website connects to the local service | Exact origin check, strong first-message token, one controller, bounds and deadlines | Compromised renderer or same-user malware can obtain a token |
| Candidate declines optional checks | Server checks granular scopes before each detector; camera excluded from score | Organization could misuse coverage; interviewer training is needed |
| Process/window metadata is spoofed | Evidence-specific wording and explicit limits | Host owner can rename software, patch APIs or run assistance elsewhere |
| Database payloads, order or tail are altered | Event chain and persisted signed checkpoint checked on append/export | Attacker who steals signing key can forge; old valid copies can be rolled back |
| A report substitutes a new key | External verifier accepts an independently pinned public key; cloud requires enrollment | Bad enrollment or stolen key defeats origin authentication |
| Monitoring becomes invisible after disconnect | Stop on socket close and a 15-second heartbeat lease | A blocked OS call may delay cleanup; test force-close paths on devices |
| Camera worker blocks | Separate process, explicit stop and bounded termination | Native capture/permission behavior differs per OS; accuracy is not established |
| Notes/metadata contain markup | HTML and PDF text escaping | Renderer dependencies and Tauri surface still require security review |
| Unintended remote upload | Desktop has no automatic upload; separate CLI consent flag and API consent field | An operator can falsely attest consent; organizational controls still matter |
| Sensitive data retained indefinitely | 24-hour expiry and deletion | Exported copies, filesystem snapshots, backups and offline devices need separate handling |

The candidate controls their own computer. This tool cannot supply hardware attestation, prove the absence of a second device or prove that the screen they share is complete. It also cannot prevent self-modification by an administrator. Tamper-evident logging is deliberately not described as tamper-proof monitoring.

## Fairness and deployment governance

Gaze, eye movement, speaking rhythm and thinking time can vary with disability, neurodivergence, language, culture, camera placement, stress, lighting and the question itself. No emotion or protected-trait inference is attempted. The camera output is a fragile experimental proxy and must not determine selection, rejection or ranking. A candidate can use the app without it.

Document the interview's permitted tools and accommodations before collecting data. Make explanations visible alongside alerts. Offer a meaningful alternative to monitoring. Do not use an index threshold as an automated rejection rule or represent the system as a lie detector.

The consent UI is a product permission mechanism, **not proof of a valid legal basis**. Employers and recruiters must assess the applicable law, necessity, proportionality, candidate rights, retention, security and any impact-assessment obligations for their own deployment. The ICO maintains relevant [employment data guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/employment/). No blanket GDPR, UK GDPR or AI-law compliance claim is made by this project.

## Platform evidence and technical references

- Microsoft's [GetWindowDisplayAffinity documentation](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowdisplayaffinity) permits querying windows from other processes but documents success conditions tied to layered windows and desktop composition. This implementation treats failed queries as unknown.
- Apple's [Quartz window metadata API](https://developer.apple.com/documentation/coregraphics/cgwindowlistcopywindowinfo(_:_:)) is the macOS entry point; this project never interprets it as a reliable inventory of every GPU-rendered layer. Verify permission behavior and available metadata on each supported macOS release.
- [Tauri Rust commands](https://v2.tauri.app/develop/calling-rust/) provide the local bootstrap and export interface. The desktop UI uses no broad shell or arbitrary-filesystem plugin.
- [Chrome's management API](https://developer.chrome.com/docs/extensions/reference/api/management) powers the candidate-operated companion. Its permission is explicit. The companion does not use content scripts or host permissions.
- [OpenCV cascade detection](https://docs.opencv.org/4.x/db/d28/tutorial_cascade_classifier.html) supplies face/eye regions; it does not validate this project's gaze proxy or its suitability for interviews.
- [WebSocket server documentation](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html) informs origin, message-size and handshake controls. The supplied dependency versions reflect the tested environment, not a claim that they are the newest or vulnerability-free releases.
- [Cluely](https://cluely.com/) and [Interview Coder](https://www.interviewcoder.co/) describe assistance products. Those descriptions are not verification of executable names, undetectability claims or detection effectiveness. Seed name rules are illustrative and must be maintained/tested; browser-based tools may have no matching process name at all.

## Release gates

Before a real interview deployment: native platform tests; camera/permissions and stop behavior; validated error rates; accessibility review; Tauri IPC/navigation audit; dependency and supply-chain review; signed/notarized distribution; protected signing keys; external checkpoint receipt if required; operational retention and identity design; and legal review of the actual deployment. None of these may be replaced by the dashboard's numeric index.

Optional dashboard focus timing (v3 consent) records departure/restoration and worker-observed intervals only, without destinations or content. Session rules, detector coverage transitions and sampled device-count changes are retained in the audit timeline. See [scenario enhancements](audits/Scenario-Enhancements.md) for scope and limitations.
