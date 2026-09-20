# Verification record

Created and checked on 13 September 2026 in a Linux development environment with Python 3.12.14, Node 24.19.0, websockets 16.0, cryptography 46.0.0 and ReportLab 4.4.9.

## Installation compatibility correction

Following a reported macOS install failure, the distributed pin was changed to `websockets==15.0.1`. Its public package metadata declares Python >=3.9, while version 16.0 requires >=3.10. The other exact core pins, cryptography 46.0.0 and ReportLab 4.4.9, were confirmed on their public PyPI release pages. The setup commands now upgrade pip and use an explicit Python 3.12 executable for new macOS environments. The offline hash helper now streams SHA-256 without the Python 3.11-only `hashlib.file_digest` helper.

The 37-test result below was obtained with websockets **16.0**, not 15.0.1. A download of 15.0.1 for isolated retesting timed out in this environment, so runtime tests with the corrected pin and on the user's macOS/Python version remain pending. The installation correction must not be described as a completed native compatibility test.

Sources: [websockets changelog](https://websockets.readthedocs.io/en/stable/project/changelog.html), [websockets 15.0.1](https://pypi.org/project/websockets/15.0.1/), [cryptography 46.0.0](https://pypi.org/project/cryptography/46.0.0/), [ReportLab 4.4.9](https://pypi.org/project/reportlab/4.4.9/).

## Original verification results

| Check | Result | Scope |
|---|---|---|
| Python automated tests | **37 passed** | Consent, disabled scopes, stop, expired heartbeat, scoring, minimization, detector errors, manual timing, signed audit and cloud report API |
| WebSocket authentication | **Passed** | Wrong token, missing/untrusted origin and a second controller are denied |
| Disconnect cleanup | **Passed with test detectors** | An active test session stops when its controller disconnects; no physical camera was exercised |
| Audit integrity | **Passed** | Altered payload/consent, reordering, truncation, wrong pinned key, direct database edits and recomputed event hashes are rejected |
| Reporting API permissions | **Passed** | Consent required; unknown key rejected; read token cannot upload/delete; upload/read/delete works locally with synthetic data |
| PDF generation | **Passed** | Valid bundle produces PDF; invalid signature is rejected |
| Sample PDF visual review | **Passed** | Two A4 pages rendered with Poppler and visually inspected; embedded fonts, no clipped text or page-number overlap |
| Offline audit verification | **Passed** | Synthetic sample signature and chain are internally consistent; no external identity attestation is claimed |
| JavaScript parse checks | **Passed** | Dashboard, demo and companion scripts pass Node syntax checks |
| Static UI build | **Passed** | Dependency-free web assets copied into `dist/` by the build script |
| Browser/UI workflow script | **Not run to completion** | Local Chromium executable absent. The managed browser denied access to the local preview with `ERR_BLOCKED_BY_CLIENT`. No rendered dashboard screenshot or browser success is claimed |
| Rust/Tauri compilation | **Not run** | Rust toolchain absent from this environment; native CI workflow supplied for later execution |
| Windows/macOS native probes | **Source supplied; unverified on real devices** | Unit tests mock Windows metadata; no actual window, audio or display APIs were exercised on either target OS |
| Camera/OpenCV accuracy and permissions | **Not tested** | OpenCV/camera unavailable; only aggregate quality logic tested; no raw camera or audio was collected |
| Companion extension in Chrome/Edge | **Not installed or runtime-tested** | Source and permission model supplied; JavaScript syntax checked |
| Docker build / remote deployment | **Not run** | Configuration supplied; reporting API tested directly on loopback; no external upload or service deployment |
| Performance / detection effectiveness | **Not measured** | No validated false-positive/false-negative rates, CPU/RAM measurements or employment-decision validity |

## Reproducing the checks

```bash
python -m unittest discover -s tests -v
node --check web/app.js
node --check web/demo.js
node --check companion/popup.js
node scripts/build.mjs
python scripts/sample_report.py
python scripts/verify_audit.py output/sample-audit.json
```

For PDF layout review, render `output/sample-report.pdf` with `pdftoppm` or open it in a PDF viewer. The sample audit's public key is generated for the fixture; never enroll that key as a real device identity.

`tests/browser.mjs` supplies consent, synthetic-mode labelling, note escaping, navigation, stop/delete, real loopback session, export and mobile-overflow checks for a machine with Playwright/Chromium installed. That script is provided as a future test, not evidence of a passed browser test here.

The source is a developer prototype. These test results establish specific implementation behavior, not real-world cheating-detection accuracy or production readiness.
