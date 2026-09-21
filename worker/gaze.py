"""Experimental eye-position proxy. Not an attention, intent, or cheating classifier.

Camera lives in a killable subprocess. No frame crosses its pipe or is saved.
OpenCV cascades locate eyes; a dark-pixel centroid is calibrated against a
candidate's comfortable screen-facing position. Glasses/lighting/head movement
can invalidate it. No individual score or adverse-decision use is supported.
"""
import multiprocessing as mp
import time
import threading
from collections import deque
from .models import Result


def aggregate(samples, baseline):
    valid = [s for s in samples if s is not None]
    if baseline is None or len(valid) < 10 or len(valid) / max(len(samples), 1) < .6:
        return {"consistency": None, "quality": "insufficient", "valid_samples": len(valid)}
    drift = [abs(x - baseline) > .09 for x in valid]
    return {"consistency": round(100 * (1 - sum(drift) / len(valid))),
            "quality": "experimental", "valid_samples": len(valid)}


def camera_loop(pipe):
    cap = None
    try:
        import cv2
        import numpy as np
        cv2.setNumThreads(1)
        face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        eye = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        if not cap.isOpened():
            raise RuntimeError("Camera unavailable or permission declined")
        samples, calibration = deque(maxlen=100), []
        baseline = None
        ema_value = None
        while True:
            if pipe.poll() and pipe.recv() == "stop":
                break
            started = time.monotonic()
            ok, frame = cap.read()
            value = None
            lighting = "normal"
            secondary_person = False
            faces_count = 0
            if ok:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                lum = float(np.mean(gray))
                if lum < 35:
                    lighting = "underexposed"
                    enhanced = gray
                elif lum > 220:
                    lighting = "overexposed"
                    enhanced = gray
                else:
                    lighting = "normal"
                    enhanced = clahe.apply(gray)
                faces = face.detectMultiScale(enhanced, 1.2, 5, minSize=(75, 75))
                faces_count = len(faces)
                if faces_count > 1:
                    secondary_person = True
                elif faces_count == 1:
                    x, y, w, h = faces[0]
                    roi = enhanced[y:y + h // 2, x:x + w]
                    eyes = eye.detectMultiScale(roi, 1.15, 5, minSize=(15, 10))
                    if len(eyes) == 2:
                        positions = []
                        for ex, ey, ew, eh in eyes:
                            crop = roi[ey + eh // 4:ey + 3 * eh // 4, ex + ew // 6:ex + 5 * ew // 6]
                            blurred = cv2.GaussianBlur(crop, (5, 5), 0)
                            _, mask = cv2.threshold(blurred, float(np.percentile(blurred, 18)), 255,
                                                    cv2.THRESH_BINARY_INV)
                            moments = cv2.moments(mask)
                            if moments["m00"]:
                                positions.append(moments["m10"] / moments["m00"] / crop.shape[1])
                        if len(positions) == 2 and abs(positions[0] - positions[1]) < .2:
                            raw_val = sum(positions) / 2
                            if ema_value is None:
                                ema_value = raw_val
                            else:
                                ema_value = 0.3 * raw_val + 0.7 * ema_value
                            value = ema_value
                del frame, gray, enhanced
            samples.append(value)
            if baseline is None and value is not None and lighting == "normal" and not secondary_person:
                calibration.append(value)
                if len(calibration) >= 50:
                    if float(np.std(calibration)) < .06:
                        baseline = float(np.median(calibration))
                    else:
                        calibration.clear()
            metrics = aggregate(samples, baseline)
            metrics["calibrated"] = baseline is not None
            metrics["calibration_samples"] = len(calibration)
            metrics["lighting"] = lighting
            metrics["secondary_person"] = secondary_person
            metrics["faces_count"] = faces_count
            pipe.send(metrics)
            time.sleep(max(0, .2 - (time.monotonic() - started)))
    except Exception:
        pipe.send({"error": "Camera or OpenCV unavailable. You can continue without gaze."})
    finally:
        if cap is not None:
            cap.release()
        pipe.close()


class GazeDetector:
    name, scope = "GazeDetector", "gaze"

    def __init__(self):
        self.lifecycle = threading.RLock()
        self.closed = False
        self.process = None
        self.pipe = None
        self.latest = {"consistency": None, "quality": "calibrating", "calibrated": False}
        self.last_update = None
        self.started_at = None
        self.failure = None

    def scan(self, context):
        with self.lifecycle:
            if self.closed:
                return Result(self.name, "error" if self.failure else "disabled",
                              self.failure or "Camera monitoring stopped.")
            return self._scan(context)

    def _scan(self, context):
        if self.process is None:
            parent, child = mp.get_context("spawn").Pipe()
            self.pipe = parent
            self.process = mp.get_context("spawn").Process(target=camera_loop, args=(child,), daemon=True)
            self.started_at = time.monotonic()
            try:
                self.process.start()
            except Exception:
                self.process = None
                parent.close()
                self.pipe = None
                return self._fail("Camera process could not start. Start a new session to retry.")
            finally:
                child.close()
        if self.pipe:
            try:
                for _ in range(10):
                    if not self.pipe.poll():
                        break
                    self.latest = self.pipe.recv()
                    self.last_update = time.monotonic()
            except (EOFError, OSError):
                return self._fail("Camera connection closed. Start a new session to retry.")
        if "error" in self.latest or not self.process.is_alive():
            return self._fail(self.latest.get("error", "Camera worker stopped. Start a new session to retry."))
        if self.last_update is None:
            if self.started_at is not None and time.monotonic() - self.started_at >= 10:
                return self._fail("Camera returned no measurements within 10 seconds. Start a new session to retry.")
            return Result(self.name, "waiting", "Waiting for the first camera measurement; coverage is unknown.")
        if time.monotonic() - self.last_update > 3:
            return self._fail("Camera measurements are stale. Start a new session to retry.")
        signals = []
        if self.latest.get("secondary_person"):
            from .detectors import signal
            signals.append(signal(
                self.name, "secondary_person", "Multiple faces observed in camera frame",
                0.85, 0.0, {"faces_detected": self.latest.get("faces_count", 2)},
                "More than one face was visible in the camera field of view.",
                "Passersby, colleagues, or family members may enter the camera frame. Excluded from index."
            ))
        return Result(self.name, "partial", "Experimental eye-position consistency; excluded from score.",
                      signals=signals, metrics=self.latest.copy())


    def _fail(self, detail):
        self.failure = detail
        self.close()
        return Result(self.name, "error", detail)

    def close(self):
        with self.lifecycle:
            self.closed = True
            if self.process is not None:
                # Enforce shutdown even when camera acquisition/read is stuck.
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=.2)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(timeout=.2)
                if self.process.is_alive():
                    raise RuntimeError("Camera worker did not exit")
                self.process = None
            if self.pipe is not None:
                self.pipe.close()
                self.pipe = None
