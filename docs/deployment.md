# Build and deployment guide

## Development requirements

- Python 3.12. The required WebSocket, cryptography and ReportLab versions are in `requirements.txt`; optional OpenCV, PortAudio bindings and macOS Quartz bindings are in `requirements-native.txt`.
- Node 22+ and Rust stable for the desktop shell. Follow [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for Windows build tools/WebView2 and macOS Xcode command-line tools.
- Browser development does not require Rust. Native platform probes require the corresponding OS; Linux is a limited developer fallback.

The source uses Tauri major-version ranges and no generated Rust/npm lockfiles because Rust/npm dependency resolution was not completed here. Resolve dependencies on a controlled build machine, review changes, commit `Cargo.lock` and `package-lock.json`, and pin the optional Python dependencies before release. The original tests used websockets 16.0; the corrected distribution pins 15.0.1 for installation compatibility with Python 3.9. Runtime retesting with this corrected pin remains pending. Dependency versions still require current vulnerability review.

## Windows

1. Prepare the virtual environment and dependencies using README instructions. Install the current supported Visual Studio C++ build tools and WebView2 per Tauri's guide.
2. Set `IIM_PYTHON` to the absolute virtual-environment Python executable.
3. Run `npm install`, `npm run desktop:dev`, then `npm run desktop:build`.
4. Build artifacts are normally under `src-tauri/target/release/bundle/`. Review the actual bundler result; no installer has been generated here.
5. Validate ordinary user permissions, denial behavior, high-DPI displays, multiple monitors, mixed architectures and camera contention during a real call.
6. Sign the final executable and installer with your organization certificate. Do not ship unsigned updates, background installation tasks or automatic elevation.

## macOS

1. Prepare Python and Xcode command-line tools. Use the appropriate Apple Silicon or Intel Python/Rust toolchain.
2. Set `IIM_PYTHON` and use `npm run desktop:dev` / `npm run desktop:build`.
3. Validate Quartz output and camera permissions on the target macOS versions. Running camera code through an external Python interpreter may attribute OS permission prompts to Python; this must be resolved before standalone distribution. The Tauri app includes a usage-description plist but that alone does not complete Python camera permission packaging.
4. For standalone distribution, bundle a reviewed Python worker using a platform-specific freezer or port the collectors to Rust. Ensure native libraries and subprocess resources resolve correctly; this source release does not include such an embedded worker.
5. Sign the complete app and all embedded components, enable the necessary hardened-runtime entitlements, notarize and staple. Test the notarized package on a clean device. See [Tauri macOS signing](https://v2.tauri.app/distribute/sign/macos/).

## Browser companion

For development, use Chrome/Edge's extension developer page and load the `companion/` folder as unpacked. The browser requests `management` permission. Candidate clicks **Review extensions**, examines the list, exports it, then imports the JSON inside the consented interview session.

Use extension-store review for production. No deployment, extension installation or permission grant was performed here. This is an inventory companion, not a locked secure browser.

## Optional reporting service with Docker

Docker hosts **only the report API**. A container cannot observe the Windows/macOS user's desktop or webcam through this design. Do not mount host processes, audio sockets, cameras or privileged devices into it.

Generate two different tokens and independently enroll an expected device public key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `REPORT_WRITE_TOKEN`, `REPORT_READ_TOKEN` and `REPORT_TRUSTED_KEYS` in a private local environment file. The last value is a JSON array of base64 Ed25519 public keys whose origin you verified separately. Do not commit credentials or a candidate's private signing key.

```bash
docker compose up --build
```

The published port binds to `127.0.0.1:8080`. Containers run as a non-root user with a read-only root filesystem, no extra capabilities and a named data volume. Docker configuration was supplied but not built in this environment.

After the candidate reviews a stopped session and authorizes the upload, an operator can run:

```bash
python scripts/upload_report.py path/to/signed-session.json \
  --url http://127.0.0.1:8080 --local-dev --consent-to-upload
```

The script reads the write token from the environment, refuses redirects and requires HTTPS for remote destinations. This command is a usage example; no report was sent externally.

Before remote hosting, place the API behind a production TLS reverse proxy with request limits/timeouts. Replace shared bearer keys with managed identities, secret rotation, per-report authorization and operational audit trails. Use one isolated service/database per tenant until genuine tenant-aware authorization is implemented. Configure expiry cleanup and encrypted backups. Do not expose Python's development HTTP server directly to the internet.

## Native acceptance checklist

| Scenario | Expected result |
|---|---|
| Launch; consent not accepted | Zero detector calls; no camera prompt or active stream |
| Only window consent | No process inventory or camera/audio-device probe |
| Stop / close window / crash / disconnect | Camera closes promptly; polling stops; gap/interruption is retained |
| Ordinary Zoom/Teams captions and controls | May create metadata observations; evidence includes legitimate alternatives |
| Harmless layered topmost test window | Observable flags match independently inspected OS metadata |
| Capture affinity query fails | Unknown capability; no false capture-exclusion claim |
| Multiple/virtual/remote displays | Record actual public metadata; unknown attribution is preserved |
| Assistive technology | Reviewable context; no automatic rejection or gaze penalty |
| Camera busy, dark scene, glasses, two faces | Missing/low-quality measurements; no suspicion penalty |
| JSON/PDF export | Signed JSON verifies; PDF reflects the same completed session; file saves in Downloads |
| Modified/reordered/truncated audit | Verification fails; no fresh signature over the alteration |
| Rollback / patched worker / stolen key | Document trust limitation; do not claim local protection against owner |
| Two-hour call | Bounded resources; clean session expiration and fresh consent required |
| 24-hour expiry / deletion | App data expires; separate exports are disclosed as separate copies |

Measure false positives with representative legitimate interviews before selecting any review workflow. No validated sensitivity, specificity, recall or false-positive rate is supplied by this project.
