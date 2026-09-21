---
name: tauri-desktop-engineering
description: Expert workflows for developing, compiling, debugging, and packaging the Tauri 2 (Rust) desktop shell for Interview Integrity Monitor. Use when modifying src-tauri, configuring IPC commands, handling native window attributes, packaging desktop installers, or bundling Python sidecars.
---

# Tauri 2 Desktop Engineering Skill

## Overview

This skill guides development, debugging, and packaging of the desktop shell located in [`src-tauri/`](file:///c:/Users/aravi/projects/interview-integrity-monitor/src-tauri). The project pairs a Rust desktop shell (Tauri 2) with a Python background worker daemon and an HTML5/CSS/JS frontend dashboard.

## When to Use

- Working on Tauri 2 configuration ([`src-tauri/tauri.conf.json`](file:///c:/Users/aravi/projects/interview-integrity-monitor/src-tauri/tauri.conf.json)) or Rust source ([`src-tauri/src/main.rs`](file:///c:/Users/aravi/projects/interview-integrity-monitor/src-tauri/src/main.rs)).
- Implementing or debugging Tauri IPC commands (e.g., file dialogs, saving PDF reports, window control).
- Managing platform-specific capabilities (Windows display affinity, macOS camera entitlements).
- Preparing distribution packages or embedding a standalone Python runtime.

## Core Commands

### Development
```powershell
# Set Python path and launch Tauri in development mode
npm install
$env:IIM_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm run desktop:dev
```

### Release Build
```powershell
# Compile release binary on the target OS
npm run desktop:build
```

### Python Sidecar Preparation
```powershell
# Verify Python runtime and required packages
npm run sidecar:verify

# Stage local virtual environment into src-tauri/binaries/python for desktop packaging/testing
npm run sidecar:prepare

# Display standalone packaging guide for production redistributables
python scripts/prepare_sidecar.py --guide
```

### Verification & Linting
```powershell
cd src-tauri
cargo check
cargo test
cargo clippy
```

## Architectural Guidelines

1. **Worker Process Lifecycle & Supervision**:
   - The Tauri shell bootstraps and monitors the Python worker process via intelligent resolution: `IIM_PYTHON` env var -> `.venv` -> `src-tauri/binaries/python` -> system `python`.
   - On Windows, child processes are assigned to a Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (0x2000). If the desktop window is closed, exits via `RunEvent::ExitRequested` or `RunEvent::Exit`, or crashes unexpectedly, the OS kernel forcefully and immediately reaps all child worker and camera processes, preventing orphaned processes.
   - On POSIX, standard graceful EOF signaling followed by bounded SIGKILL teardown is enforced.

2. **IPC & Security Boundaries**:
   - Limit Tauri commands to local, candidate-operated actions (e.g., explicit "Save Report to File" dialogs).
   - Never allow arbitrary shell execution from the web dashboard.
   - Enforce Content Security Policy (CSP) defined in `tauri.conf.json`.

3. **Standalone Packaging (Python Sidecar)**:
   - For standalone distribution without requiring manual Python installation, package a portable Python runtime using `astral-sh/python-build-standalone`.
   - Place the portable runtime under `src-tauri/binaries/python` and configure Tauri resources in `tauri.conf.json`.
   - Use `scripts/prepare_sidecar.py` to automate staging and dependency verification.
