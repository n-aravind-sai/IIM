# F08 — Browser regression assertion

Status: outdated assertion fixed; full browser execution pending CI.

The dashboard exposes escaped detector identity and status attributes. The browser flow waits for ProcessDetector's `partial` status instead of the obsolete phrase "Executable names only". The native test explicitly selects processes and disables every other scope, preventing unintended camera/microphone use. A Linux GitHub Actions job installs Chromium and runs the existing consent, demo, note escaping, stop/delete, real worker, PDF/JSON download and mobile layout flow.

Local JavaScript syntax checks passed. Launching the browser test was attempted but Chromium is absent from this environment; this is not a passing end-to-end result. CI and native-device verification are reported separately in the final audit.
