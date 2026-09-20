# Technical Improvement Roadmap & GitHub Research

This document compiles technical improvements, architectures, and open-source libraries gathered from GitHub and the computer vision/anti-cheat engineering ecosystem. These upgrades address the prototype boundaries documented in [`README.md`](./README.md#capability-boundaries), moving the project toward a production-grade, privacy-first integrity monitoring platform.

---

## Table of Contents
1. [Computer Vision & Gaze Tracking](#1-computer-vision--gaze-tracking)
2. [Audio & Acoustic Intelligence](#2-audio--acoustic-intelligence)
3. [Operating System & Overlay Detection](#3-operating-system--overlay-detection)
4. [Desktop Architecture & Standalone Packaging (Tauri 2)](#4-desktop-architecture--standalone-packaging-tauri-2)
5. [Hardware Attestation & Cryptographic Hardening](#5-hardware-attestation--cryptographic-hardening)
6. [Companion Extension & Browser Security](#6-companion-extension--browser-security)
7. [Implementation Priority Matrix](#7-implementation-priority-matrix)

---

## 1. Computer Vision & Gaze Tracking

### Current Limitations ([`worker/gaze.py`](./worker/gaze.py))
* Relies on basic OpenCV Haar cascades and 2D bounding boxes.
* Sensitive to lighting changes, head tilts, and webcam placement.
* Calibration frequently fails or requires rigid head positioning.
* Does not detect secondary persons, phones, or external screens.

### GitHub Improvements & Solutions

#### A. 3D Iris Landmark & Gaze Vector Estimation
* **Reference Projects:**
  * [`google-ai-edge/mediapipe`](https://github.com/google-ai-edge/mediapipe) (Face Mesh + Iris)
  * [`alireza787b/Python-Gaze-Face-Tracker`](https://github.com/alireza787b/Python-Gaze-Face-Tracker)
  * [`Lark-Alfen/GazeMetric`](https://github.com/Lark-Alfen/GazeMetric)
  * [`Ahmednull/L2CS-Net`](https://github.com/Ahmednull/L2CS-Net)
* **Improvements:**
  * Use MediaPipe 468-point 3D Face Mesh with 10 refined Iris landmarks (points 468–477).
  * Calculate Euclidean eye-to-iris ratios for horizontal and vertical gaze vectors.
  * Provide continuous normalized gaze coordinates `(gaze_x, gaze_y)` relative to screen boundaries.
  * Keep all processing in-memory with zero frame retention to maintain candidate privacy.

#### B. 3D Head Pose Estimation (Yaw, Pitch, Roll)
* **Implementation:**
  * Map 6 2D facial landmarks (nose tip, chin, eye corners, mouth corners) against a generic 3D facial model using OpenCV `cv2.solvePnP`.
  * Compute Euler angles (yaw, pitch, roll) to distinguish between natural eye movements (reading a question) vs. physically looking away from the workstation.

#### C. Secondary Person & Prohibited Object Detection
* **Reference Projects:**
  * [`ultralytics/ultralytics`](https://github.com/ultralytics/ultralytics) (YOLOv8 / YOLOv11 Nano models)
  * [`vardanagarwal/Proctoring-AI`](https://github.com/vardanagarwal/Proctoring-AI)
* **Improvements:**
  * Run an ultra-lightweight quantized object detection model (`yolov8n.onnx` or `yolov11n.onnx`) running at 5–10 FPS on CPU.
  * Emit events when:
    * `count(face) > 1` (secondary individual in camera view).
    * `detected(cell phone, earphone, second display)` with confidence threshold > 0.6.

---

## 2. Audio & Acoustic Intelligence

### Current Limitations ([`worker/detectors.py`](./worker/detectors.py))
* Only queries audio input device names and static background process names.
* Opens no audio streams and cannot detect unauthorized background whispering or third-party assistance.

### GitHub Improvements & Solutions

#### A. Privacy-Preserving Voice Activity Detection (VAD)
* **Reference Project:** [`snakers4/silero-vad`](https://github.com/snakers4/silero-vad)
* **Improvements:**
  * Process microphone input strictly as rolling PCM buffers; do **not** record or store conversation audio.
  * Calculate probability of speech activity in 30ms chunks.
  * Flag prolonged candidate silence when verbal questions are being asked, or unexpected speech bursts during offline coding challenges.

#### B. Speaker Diarization / Multiple Speaker Detection
* **Reference Project:** [`pyannote/pyannote-audio`](https://github.com/pyannote/pyannote-audio)
* **Improvements:**
  * Identify vocal pitch and embedding vectors during an initial test sentence.
  * Detect when a second acoustic profile is present in the room (co-pilot prompting).

---

## 3. Operating System & Overlay Detection

### Current Limitations ([`worker/native.py`](./worker/native.py))
* Uses public Win32 APIs and macOS Quartz metadata polled every 2 seconds.
* Cannot inspect GPU composited overlays, DirectX/Vulkan hooks, or short-lived floating windows.

### GitHub Improvements & Solutions

#### A. Native Rust Win32 Hooking Layer
* **Reference Project:** [`microsoft/windows-rs`](https://github.com/microsoft/windows-rs)
* **Improvements:**
  * Move window polling from Python `ctypes` into the compiled Tauri Rust layer ([`src-tauri`](./src-tauri)).
  * Use `RegisterShellHookWindow` and `SetWinEventHook` to receive zero-latency push events when windows gain focus, change z-order, or adjust transparency.
  * Query `GetWindowDisplayAffinity` reliably to flag windows that intentionally hide themselves from screen recording (`WDA_EXCLUDEFROMCAPTURE` / `WDA_MONITOR`).

#### B. Virtual Screen & Hardware Capture Detection
* **Implementation:**
  * Query Windows `EnumDisplayDevices` and EDID registers to distinguish physical HDMI/DisplayPort monitors from virtual software display drivers (e.g., OBS Virtual Cam, spacedesk, Duet Display).

---

## 4. Desktop Architecture & Standalone Packaging (Tauri 2)

### Current Limitations ([`src-tauri`](./src-tauri))
* Requires a pre-installed Python 3.12 environment and `$env:IIM_PYTHON` path.
* Not packaged into a standalone self-contained installer.

### GitHub Improvements & Solutions

#### A. Embedded Portable Python Sidecar
* **Reference Project:** [`indygreg/python-build-standalone`](https://github.com/indygreg/python-build-standalone)
* **Improvements:**
  * Bundle a standalone, relocatable Python 3.12 runtime directly inside Tauri's resource directory.
  * Eliminate the prerequisite for candidates to manually install Python, pip, or virtual environments.
  * Use `tauri-plugin-shell` to spawn the bundled Python worker as an isolated sidecar.

#### B. Automated Multi-Platform CI/CD
* **Reference Project:** [`tauri-apps/tauri-action`](https://github.com/tauri-apps/tauri-action)
* **Improvements:**
  * Set up GitHub Actions matrix builds for Windows (`.msi`, `.exe`) and macOS (`.dmg`, signed with Developer ID).
  * Automatically code-sign releases and generate checksum manifests.

---

## 5. Hardware Attestation & Cryptographic Hardening

### Current Limitations ([`worker/audit.py`](./worker/audit.py))
* Local Ed25519 private keys are stored on disk in SQLite or local state files.
* A hostile device owner with administrative privileges can alter Python memory or steal the local signing key.

### GitHub Improvements & Solutions

#### A. TPM 2.0 / OS Credential Vault Key Storage
* **Reference Projects:**
  * [`tpm2-software/tpm2-pytss`](https://github.com/tpm2-software/tpm2-pytss) (TPM 2.0 bindings)
  * Windows DPAPI / Cryptography Next Generation (CNG) via Rust
  * macOS Keychain Services API
* **Improvements:**
  * Store the private signing key in the hardware security module (TPM) or OS secure enclave.
  * Ensure private keys cannot be extracted from disk or RAM dumps.

#### B. Merkle Tree Checkpoint Proofs
* **Improvements:**
  * Transition from linear hash chains to append-only Merkle Trees.
  * Allow generating compact inclusion proofs for specific incident timestamps without revealing the candidate's entire telemetry history.

---

## 6. Companion Extension & Browser Security

### Current Limitations ([`companion/`](./companion))
* Operates on candidate-reviewed manual export and import.
* Only checks one profile and cannot verify browser environment integrity.

### GitHub Improvements & Solutions

#### A. Native Messaging Host
* **Implementation:**
  * Connect the Chrome/Edge extension directly to the Tauri desktop app via Chrome Native Messaging (`stdin`/`stdout` JSON channel).
  * Continuously verify active extensions, developer mode flags, and DevTools status without requiring manual file copy/paste.

#### B. Anti-Tamper Extension Heartbeat
* **Implementation:**
  * Issue periodic cryptographic nonces from the desktop app to the extension.
  * Ensure extension cannot be spoofed or paused during the session.

---

## 7. Implementation Priority Matrix

| Phase | Category | Improvement | Impact | Complexity | Recommended GitHub Tool / Library |
|:---:|:---|:---|:---:|:---:|:---|
| **P1** | **Computer Vision** | Upgrade Gaze Tracking to MediaPipe Face Mesh & Iris | High | Medium | `google-ai-edge/mediapipe` |
| **P1** | **Desktop Shell** | Embed Python Runtime with Tauri Sidecar | High | Medium | `indygreg/python-build-standalone` |
| **P2** | **Audio** | Add Privacy-Preserving Voice Activity Detection | High | Medium | `snakers4/silero-vad` |
| **P2** | **Computer Vision** | Secondary Person & Phone Detection via Edge YOLO | High | Medium | `ultralytics/ultralytics` |
| **P2** | **Window Survelliance**| Native Rust Win32 Hooks for Overlay & Display Affinity | Medium | Medium | `microsoft/windows-rs` |
| **P3** | **Security / Crypto** | Hardware Key Attestation (TPM 2.0 / DPAPI / Keychain)| Medium | High | `tpm2-pytss` / `windows-rs` |
| **P3** | **Browser Extension** | Native Messaging Host Integration | Medium | Medium | Chrome Native Messaging Protocol |
