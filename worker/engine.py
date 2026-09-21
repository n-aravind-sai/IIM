import copy
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict
from .audit import AuditStore, now
from .detectors import registry
from .models import Result, score

SCOPES = ("processes", "windows", "audio_devices", "displays", "extensions", "gaze")
DISCLOSURE = "iim-consent-1"


class Engine:
    def __init__(self, directory, factory=registry):
        self.lock = threading.RLock()
        self.poll_lock = threading.Lock()
        self.stopping = False
        self.store = AuditStore(directory)
        self.factory = factory
        self.detectors = []
        self.session = None
        self.active = False
        self.consent = {}
        self.context = {}
        self.results = []
        self.timeline = deque(maxlen=100)
        self.history = deque(maxlen=120)
        self.known = set()
        self.observed = {}
        self.question_at = None
        self.last_seen = 0
        self.start_time = 0
        self.last_scans = {}
        self.last_audit = 0
        self.last_prune = 0

    def start(self, consent):
        with self.lock:
            if self.active or self.stopping:
                raise ValueError("Stop the current session first")
            if not isinstance(consent, dict) or consent.get("accepted") is not True or consent.get("version") != DISCLOSURE:
                raise ValueError("Candidate acceptance of the current disclosure is required")
            if any(not isinstance(consent.get(s, False), bool) for s in SCOPES):
                raise ValueError("Invalid monitoring scope")
            consent = {"accepted": True, "version": DISCLOSURE, **{s: consent.get(s, False) for s in SCOPES}}
            if not any(consent[s] for s in SCOPES):
                raise ValueError("Select at least one disclosed monitoring scope")
            self.session = str(uuid.uuid4())
            self.consent = consent
            self.store.create(self.session, consent)
            self.detectors = self.factory()
            self.active = True
            self.last_seen = self.start_time = time.monotonic()
            self.context, self.last_scans = {}, {}
            self.last_audit = 0
            self.results, self.known = [], set()
            self.observed = {}
            self.timeline.clear()
            self.history.clear()
            self.question_at = None
            self._event("Session started", "Candidate selected monitoring scopes.", persist=False)
            return self.snapshot()

    def _event(self, title, detail, persist=True):
        event = {"time": now(), "title": title, "detail": detail}
        self.timeline.appendleft(event)
        if persist and self.session:
            self.store.append(self.session, "timeline", event)

    def heartbeat(self):
        with self.lock:
            if self.active:
                self.last_seen = time.monotonic()
            return {"active": self.active}

    def watchdog(self):
        with self.lock:
            if not self.active:
                return
            tick = time.monotonic()
            session = self.session
            reason = None
            if tick - self.last_seen > 15:
                reason = "Candidate dashboard disconnected or heartbeat expired"
            elif tick - self.start_time > 2 * 3600:
                reason = "Two-hour session limit reached; fresh consent is required"
        if reason:
            self.stop(reason, expected_session=session)

    def poll(self):
        self.watchdog()
        # A concurrent caller never queues behind a native scan.
        if not self.poll_lock.acquire(blocking=False):
            return self.snapshot()
        try:
            return self._poll()
        finally:
            self.poll_lock.release()

    def _poll(self):
        with self.lock:
            if time.monotonic() - self.last_prune > 60:
                self.store.prune()
                self.last_prune = time.monotonic()
            if not self.active:
                return self.snapshot()
            session, tick = self.session, time.monotonic()
            detectors = list(self.detectors)
            consent, context = self.consent.copy(), copy.deepcopy(self.context)
            prior = {r.detector: r for r in self.results}
            last_scans = self.last_scans.copy()
        results, scanned = [], {}
        for detector in detectors:
            with self.lock:
                if not self.active or self.session != session:
                    return self.snapshot()
            if not consent.get(detector.scope):
                result = Result(detector.name, "disabled", "Candidate did not enable this scope.")
            elif tick - last_scans.get(detector.name, -1000) < (2 if detector.scope in ("windows", "gaze") else 10):
                result = prior.get(detector.name, Result(detector.name, "disabled", "Waiting for first sample"))
            else:
                try:
                    result = detector.scan(context)
                except (ImportError, NotImplementedError):
                    result = Result(detector.name, "unsupported", "Required platform API or optional dependency is unavailable.")
                except Exception:
                    result = Result(detector.name, "error", "Probe failed or permission was denied; coverage is unknown.")
                scanned[detector.name] = tick
            results.append(result)
        with self.lock:
            if not self.active or self.session != session:
                return self.snapshot()
            # An import arriving during a scan must remain due for the next poll.
            if self.context != context:
                scanned.pop("BrowserExtensionDetector", None)
            new = {s.id: asdict(s) for r in results for s in r.signals}
            # Persist full minimized evidence BEFORE publishing the snapshot.
            # A changed signal with the same ID also gets a new signed event.
            for identity, signal in new.items():
                if self.observed.get(identity) != signal:
                    self.store.append(self.session, "signal_observed", {"signal": signal})
                    self._event(signal["title"], signal["explanation"])
            for identity in sorted(self.known - new.keys()):
                self.store.append(self.session, "signal_resolved", {
                    "signal_id": identity, "reason": "No longer returned; observation or coverage changed"})
                self._event("Observation or coverage changed", "Check detector coverage; the previous observation remains in the audit history.")
            gaze = next((r.metrics.get("consistency") for r in results if r.detector == "GazeDetector"), None)
            point = {"time": now(), "score": score(results)["value"], "gaze": gaze}
            self.history.append(point)
            if tick - self.last_audit >= 10:
                self.store.append(self.session, "sample", {"score": score(results), "results": [r.json() for r in results]})
                self.last_audit = tick
            self.last_scans.update(scanned)
            self.results, self.known, self.observed = results, set(new), new
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            return {"session_id": self.session, "active": self.active, "consent": self.consent,
                    "time": now(), "score": score(self.results), "results": [r.json() for r in self.results],
                    "timeline": list(self.timeline), "history": list(self.history),
                    "public_key": self.store.public_key_base64,
                    "head": self.store.get_head(self.session) if self.session else None,
                    "elapsed_seconds": round(time.monotonic() - self.start_time) if self.active else 0}

    def attestation(self):
        with self.lock:
            if not self.session:
                raise ValueError("No active or recent session to attest")
            head = self.store.get_head(self.session)
            pk = self.store.public_key_base64
            from .audit import canonical
            from .report import generate_qr_svg
            payload = canonical({"id": self.session, "pk": pk, "head": head})
            svg = generate_qr_svg(payload)
            return {"session_id": self.session, "public_key": pk, "head": head, "payload": payload, "svg": svg}

    def stop(self, reason="Candidate stopped monitoring", expected_session=None):
        with self.lock:
            if expected_session is not None and self.session != expected_session:
                return self.snapshot()
            if self.stopping:
                raise ValueError("Device cleanup is still in progress; close the app if it does not finish")
            if not self.active:
                return self.snapshot()
            self.active = False
            self.stopping = True
            detectors = list(self.detectors)
        failures = []
        try:
            # Device shutdown does not wait for a scan or an audit write.
            for detector in detectors:
                try:
                    detector.close()
                except Exception:
                    failures.append(detector.name)
            with self.lock:
                if failures:
                    reason += "; cleanup failed for: " + ", ".join(failures)
                self.store.append(self.session, "sample", {"score": score(self.results), "results": [r.json() for r in self.results]})
                for identity in sorted(self.known):
                    self.store.append(self.session, "signal_resolved", {
                        "signal_id": identity, "reason": "Monitoring stopped; observation tracking ended"})
                self.store.stop(self.session, reason)
                self._event("Monitoring stopped", reason, persist=False)
                self.context.clear()
                self.question_at = None
        finally:
            with self.lock:
                # A failed cleanup blocks new sessions; do not claim safe restart.
                self.stopping = bool(failures)
        if failures:
            raise RuntimeError("Device cleanup failed; close the desktop application")
        return self.snapshot()

    def import_extensions(self, entries, digest=None):
        with self.lock:
            if not self.active or not self.consent.get("extensions"):
                raise ValueError("Active session and extension-inventory consent are required")
            from .inventory import validate_inventory
            clean, checked = validate_inventory(entries, digest)
            detail = ("Candidate supplied an inventory with a matching content checksum; authenticity and completeness are unverified."
                      if checked else "Candidate supplied an inventory without a checksum; authenticity and completeness are unverified.")
            self.context["extensions"] = clean
            self.last_scans.pop("BrowserExtensionDetector", None)
            self._event("Extension inventory imported", detail)
            return {"imported": len(clean), "verified": checked, "checksum_verified": checked, "browser_authenticated": False}

    def note(self, text):
        with self.lock:
            if not self.active or not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
                raise ValueError("An active session and a note of 1–500 characters are required")
            self._event("Candidate context", text.strip())
            return {"saved": True}

    def mark(self, kind):
        with self.lock:
            if not self.active:
                raise ValueError("Start a session first")
            if kind == "question_end":
                self.question_at = time.monotonic()
                self._event("Question finished", "Manually marked by the dashboard operator.")
            elif kind == "answer_start" and self.question_at is not None:
                latency = round(time.monotonic() - self.question_at, 2)
                self._event("Answer started", f"Manual interval: {latency}s. Not scored; no inference of AI use.")
                self.question_at = None
            else:
                raise ValueError("Mark a question end before marking the answer start")
            return self.snapshot()

    def export(self):
        with self.lock:
            if self.session is None:
                raise ValueError("No session to export")
            return self.store.export(self.session)

    def delete(self):
        with self.lock:
            if self.active or self.stopping:
                raise ValueError("Stop monitoring before deleting session data")
            if self.session:
                self.store.delete(self.session)
            self.session, self.consent, self.results, self.context = None, {}, [], {}
            self.timeline.clear()
            self.history.clear()
            return self.snapshot()
