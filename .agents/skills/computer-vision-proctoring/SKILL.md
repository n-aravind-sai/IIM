---
name: computer-vision-proctoring
description: Workflows for implementing, calibrating, and benchmarking computer vision detectors in Interview Integrity Monitor. Use when working with worker/gaze.py, OpenCV, MediaPipe FaceMesh/Iris, gaze drift heuristics, face detection, camera calibration, lighting robustness, or secondary person/device detection.
---

# Computer Vision Proctoring Skill

## Overview

This skill guides the implementation, testing, and enhancement of camera-based behavioral observation modules in [`worker/gaze.py`](file:///c:/Users/aravi/projects/interview-integrity-monitor/worker/gaze.py). The system collects privacy-first, non-destructive metrics without saving or streaming candidate video frames.

## When to Use

- Updating or debugging the camera observation subprocess in [`worker/gaze.py`](file:///c:/Users/aravi/projects/interview-integrity-monitor/worker/gaze.py).
- Upgrading from basic Haar cascades to MediaPipe Face Mesh / Iris tracking.
- Tuning calibration thresholds (baseline drift, minimum stable frame samples).
- Adding secondary person or unauthorized device detection (YOLOv8/v11 Nano).
- Resolving camera initialization, lighting variation, or frame-rate stability issues.

## Core Rules & Privacy Guarantees

1. **In-Memory Frame Processing Only**:
   - Camera frames must **never** be saved to disk, recorded to video files, or transmitted across the network.
   - Only derived numeric metrics (e.g., eye-drift ratio, confidence score, calibration status) are emitted to the event stream.

2. **Isolated Subprocess Execution**:
   - Always run camera capture in a dedicated `multiprocessing.Process` communicating via `multiprocessing.Queue`.
   - Never run blocking OpenCV capture loops (`cv2.VideoCapture.read()`) on the main asyncio event loop.

3. **Conservative Calibration Protocol**:
   - Require a minimum of 50 stable, centered gaze samples (~10 seconds at 5 FPS) before marking calibration valid.
   - If lighting is insufficient (extreme underexposure) or face is obstructed, reject calibration cleanly with informative diagnostic status.

## Upgrading to MediaPipe Face Mesh / Iris

When transitioning from OpenCV Haar cascades to MediaPipe:
1. Use `mediapipe.solutions.face_mesh` with `refine_landmarks=True` (indices 468–477 for iris landmarks).
2. Compute Euclidean distance ratio between iris center and medial/lateral canthi for robust horizontal and vertical gaze vectors.
3. Calculate Head Pose using `cv2.solvePnP` with canonical 3D facial landmark points to detect head turning vs. screen engagement.

## Verification & Testing
```powershell
# Run the worker detector unit tests
python -m unittest discover -s tests -p "test_*.py" -v
```
