# Interview Integrity Monitor

Privacy-first desktop **developer prototype** for Windows and macOS. It collects disclosed technical metadata, displays reviewable observations, and produces a signed audit export and a readable PDF. It does not determine whether someone is cheating.

**Latest code audit:** [Remaining fixes and verification](docs/audits/Remaining-Fixes-Report.md).

**Release status:** runnable Python worker and browser development UI; Tauri/Rust desktop source is provided but has not been compiled on this environment. This is not a signed, standalone installer or a production-validated detector. Native Windows/macOS probes, camera accuracy, installer behavior and real interview performance require target-device validation. The advanced detection limits below are intentional and visible in the product.

## Quick start

From the extracted project directory, use Python 3.12 and a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-native.txt
python scripts/dev.py
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-native.txt
python scripts/dev.py
```

Open `http://127.0.0.1:1420` in your browser. Select **Start a session**, choose the monitoring scopes, accept the disclosure, then start. No session detector runs before acceptance. The separate **Preview camera & microphone** action opens local camera/microphone streams without recording or saving them; synthetic demo never opens devices. Camera consent (`iim-consent-3`) covers eye-position consistency, quality/calibration statistics, lighting, face count and multiple-face observations, all excluded from the index. Optional camera calibration needs at least 50 stable valid samples, approximately 10 seconds at the configured 5 FPS, and can take longer or fail.

If optional native packages are unavailable, install `requirements.txt`. Core sessions, exports, audit verification and development process enumeration remain usable; unavailable detectors are labelled explicitly.

### Fix for the original websockets installation error

The first archive pinned `websockets==16.0`. That release requires Python 3.10+, so pip may omit it from the compatible-version list when the virtual environment uses Python 3.9. This archive instead pins `websockets==15.0.1`, which supports Python 3.9 and the APIs used by this worker. Python 3.12 remains the development target; a successful dependency install does not establish full native-platform compatibility.

To fix an already extracted copy on macOS, run these commands from its project folder with the virtual environment active:

```bash
python --version
python -m pip install --upgrade pip setuptools wheel
sed -i '' 's/^websockets==16\.0$/websockets==15.0.1/' requirements.txt
python -m pip install -r requirements-native.txt
python scripts/dev.py
```

Upgrading pip alone does not change the Python version of an existing virtual environment. If installation still fails, retain the new error and `python --version` output before changing other dependencies.

References: [websockets release notes](https://websockets.readthedocs.io/en/stable/project/changelog.html), [15.0.1 package metadata](https://pypi.org/project/websockets/15.0.1/).

### UI-only synthetic demo

```bash
python3 -m http.server 1420 --bind 127.0.0.1 --directory web
```

Open `http://127.0.0.1:1420/?demo=1`. The demo is visibly labelled, uses synthetic observations, never opens devices, and exports an **unsigned demo JSON**, not a real audit. PDF generation needs the real local worker. Static preview can also use `npm run demo` inside an activated Python environment.

### Desktop development

Install the [Tauri platform prerequisites](https://v2.tauri.app/start/prerequisites/), Rust stable and Node 22+. Then, with the Python environment prepared:

```bash
npm install
export IIM_PYTHON="$PWD/.venv/bin/python"
npm run desktop:dev
```

Windows PowerShell uses:

```powershell
npm install
$env:IIM_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm run desktop:dev
```

Stop the separate browser-development launcher before starting desktop development because both use port 1420. A release build uses `npm run desktop:build` **on the target operating system**. This version still requires the configured Python environment; it does not embed Python. See [deployment](docs/deployment.md) before distributing it.

## What is included

- Tauri 2 / Rust desktop lifecycle, restricted local bootstrap and explicit report save command.
- Dependency-free HTML/CSS/JavaScript dashboard with real WebSocket updates, observation details, capability status, candidate context, timeline, session summary and responsive layouts.
- Python WebSocket worker with six modular detectors and public Windows/macOS metadata probes.
- Optional OpenCV subprocess with in-memory frames, conservative calibration and quality rejection.
- Granular consent, a persistent visible stop control, 15-second heartbeat expiry, session duration limits and local deletion.
- SQLite schema, hash-chained events and persisted Ed25519 checkpoints, plus an offline verifier.
- ReportLab PDF export, a synthetic sample report and a synthetic signed audit fixture.
- Candidate-operated Chrome/Edge extension inventory companion.
- Optional single-tenant reporting API, explicit upload script, Dockerfile and Compose configuration.
- Security-focused tests, browser workflow test script, platform acceptance checklist and release guidance.

## Capability boundaries

| Requested area | This implementation | Limit |
|---|---|---|
| Topmost / transparent overlays | Public Win32 attributes; Quartz stacking/alpha metadata | Metadata heuristics, not reliable identification of intent or all rendering paths |
| Capture exclusion flags | Windows `GetWindowDisplayAffinity`, where the query succeeds | Unknown on failure; no equivalent claim on macOS |
| Rapid overlay changes | Changed membership across 2-second samples | Shorter-lived changes can be missed |
| Hidden GPU overlays / compositor tampering | Explicitly unsupported | No hooks, injection, drivers or renderer introspection |
| Suspicious processes | Configurable exact executable-name matches | Rename/spoofing, browser-based tools and actual use cannot be established |
| Audio conflicts / multiple listeners / STT | Device-name inventory and process-name hints only | **No actual listener attribution or conflict detection**; the inventory detector opens no audio; optional pre-flight microphone preview is local and never recorded |
| Virtual / hidden displays | Active-adapter metadata; limited Windows name/flag hints | No reliable hidden-hardware detection; macOS virtual attribution unknown |
| Browser extensions | Candidate-reviewed companion export/import | One profile; self-reported; no assertion of freshness or completeness |
| Gaze / eye drift | Experimental calibrated horizontal eye-position consistency | Not robust gaze direction, attention, reading, emotion or intent detection |
| Answer latency | Manual question-end / answer-start markers | Not automatic; no robotic-response or AI-speech classifier |
| Trust score | Transparent technical heuristic with separate coverage | Not a validated probability; no hiring decision or candidate ranking |
| Screenshot integrity | Offline file digest helper | Proves equality to trusted reference bytes only, not capture completeness |
| Secure browser | Minimal inventory companion | No kiosk lockdown, browsing surveillance or browser attestation |
| Anti-tamper | Signed, chained logs checked before append/export | A hostile device owner can patch the app or steal the local signing key |
| Interviewer dashboard | Candidate can share the local dashboard through the interview call | No internet live-view relay or remote interviewer control |
| Cloud reporting | Separate opt-in API with enrolled public keys | Single-tenant reference service; production identity/TLS/ops need deployment work |

## Run verification

```bash
python -m unittest discover -s tests -v
npm run build
python scripts/verify_audit.py output/sample-audit.json
```

To run the provided browser regression script on a machine with Chromium:

```bash
npm install --no-save playwright
npx playwright install chromium
python scripts/dev.py
# In a second terminal:
node tests/browser.mjs
```

The browser script uses synthetic observations and a development process-only session; it never enables a real camera or microphone. See [verification results](docs/verification.md) for exactly what was and was not tested during creation.

## Project map

| Path | Purpose |
|---|---|
| `src-tauri/` | Rust shell, Tauri config, local capabilities, macOS camera disclosure |
| `web/` | Dashboard, styles, WebSocket client, isolated synthetic demo |
| `worker/engine.py` | Consent/session state machine and scheduler |
| `worker/detectors.py` | Registry and metadata detector modules |
| `worker/native.py` | Public platform-specific metadata collectors |
| `worker/gaze.py` | OpenCV camera subprocess and aggregate quality checks |
| `worker/audit.py` / `schema.sql` | Durable events, signing and verification |
| `worker/server.py` | Authenticated local WebSocket API |
| `worker/report.py` | Verified-bundle PDF renderer |
| `companion/` | Candidate-operated browser inventory extension |
| `cloud/` | Optional report API and its separate database schema |
| `scripts/` | Development launcher, build, upload, verification and screenshot-digest tools |
| `tests/` | Python security/behavior tests and browser regression script |
| `docs/` | Architecture, API, security, deployment, support and verification details |
| `output/` | Synthetic example PDF and audit fixture; no candidate data |

Start with [architecture](docs/architecture.md), [API design](docs/api.md), [security](docs/security.md) and [deployment](docs/deployment.md).

Optional dashboard focus timing (v3 consent) records departure/restoration and worker-observed intervals only, without destinations or content. Session rules, detector coverage transitions and sampled device-count changes are retained in the audit timeline. See [scenario enhancements](docs/audits/Scenario-Enhancements.md) for scope and limitations.
