# F01 — Device cleanup audit

Status: fixed in code; 10 automated lifecycle checks passed.

A generation token invalidates pending permission requests. Late streams have every track stopped before attachment. Reopened dialogs reject old completions and old queued close events. Stop monitoring and page exit also release browser devices, the audio context, animation callbacks and preview references. Demo pre-flight is hardware-free.

Verification: `node --test tests/preflight.mjs` passed all 10 tests using production dashboard handlers with mocked DOM, devices and RPC. Cases include delayed permission after close, overlapping reopen, duplicate open, stale rejection, enumeration failure, pagehide/beforeunload while pending and active, stop with failed RPC, native dialog close and demo isolation. These tests run in CI.

Audit conclusion: the reproduced late-permission leak is closed. Actual Chromium/Tauri permission UI and physical Windows/macOS camera and microphone release still require hardware validation. This does not close the remaining F05 disclosure issues.
