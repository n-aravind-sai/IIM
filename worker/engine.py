import copy
import threading
import time
import uuid
import secrets
from collections import deque
from concurrent.futures import Future
from dataclasses import asdict
from .audit import AuditStore, now
from .detectors import registry
from .models import Result, score
from .coverage import CoverageTracker
from .policy import normalize_policy, apply_policy
from .correlation import review_groups

SCOPES = ("processes", "windows", "audio_devices", "displays", "extensions", "gaze", "remote_sessions")
DISCLOSURE = "iim-consent-4"


class Engine:
    def __init__(self, directory, factory=registry):
        self.lock = threading.RLock()
        self.poll_lock = threading.Lock()
        self.stopping = False
        self.stop_result = None
        self.coverage = CoverageTracker()
        self.store = AuditStore(directory)
        self.factory = factory
        self.detectors = []
        self.session = None
        self.active = False
        self.consent = {}
        self.policy = None
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
        self.sample_clocks = {}
        self.last_audit = 0
        self.last_prune = 0

    def start(self, consent, policy=None):
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
            policy = normalize_policy(policy)
            session = str(uuid.uuid4())
            detectors = self.factory()
            coverage = CoverageTracker()
            started = time.monotonic()
            initial_timeline = []
            created = False
            def record_gap(kind, data):
                self.store.append(session, kind, data)
                title, detail = self._coverage_notice(kind, data)
                initial_timeline.append({'time': now(), 'title': title, 'detail': detail})
            try:
                self.store.create(session, consent)
                created = True
                self.store.append(session, 'session_policy', policy)
                for detector in detectors:
                    if consent.get(detector.scope):
                        coverage.observe(Result(detector.name, 'waiting', 'Waiting for the first measurement.'),
                                         detector.scope, started, now(), record_gap, boundary='session_start')
            except BaseException:
                cleanup_failed = False
                for detector in detectors:
                    try:
                        detector.close()
                    except Exception:
                        cleanup_failed = True
                if created:
                    try:
                        self.store.stop(session, 'Session startup failed before monitoring was enabled')
                    except Exception:
                        pass  # Next successful startup marks this record interrupted.
                if cleanup_failed:
                    self.stopping = True
                    self.stop_result = Future()
                    self.stop_result.set_exception(RuntimeError('Startup cleanup failed; close the application'))
                raise
            # Publish only after all required startup records are durable.
            self.session, self.consent, self.policy = session, consent, policy
            self.detectors, self.coverage = detectors, coverage
            self.stop_result = None
            self.active = True
            self.last_seen = self.start_time = started
            self.context, self.last_scans = {}, {}
            if consent['processes'] and consent['windows']:
                self.context['process_link_key'] = secrets.token_bytes(32)
            self.sample_clocks = {}
            self.last_audit = 0
            self.results, self.known = [], set()
            self.observed = {}
            self.timeline.clear()
            self.history.clear()
            self.question_at = None
            self._event("Session started", "Candidate selected monitoring scopes.", persist=False)
            self.timeline.extendleft(initial_timeline)
            return self.snapshot()

    @staticmethod
    def _coverage_notice(kind, data):
        if kind == "coverage_gap_closed":
            recovered = data["end_reason"] == "measurements_resumed"
            title = "Measurements resumed" if recovered else "Coverage gap ended"
            detail = f"{data['detector']}: {data['duration_seconds']}s unavailable. "
            detail += "Limited measurements are available again." if recovered else "Monitoring stopped; recovery was not established."
        else:
            title = "Coverage unavailable" if kind == "coverage_gap_opened" else "Coverage status changed"
            detail = f"{data['detector']}: {data['detail']} Missing measurements remain unknown."
        return title, detail

    def _coverage_event(self, kind, data):
        self.store.append(self.session, kind, data)
        self._event(*self._coverage_notice(kind, data), persist=False)

    def _event(self, title, detail, persist=True):
        event = {"time": now(), "title": title, "detail": detail}
        if persist and self.session:
            self.store.append(self.session, "timeline", event)
        self.timeline.appendleft(event)

    def update_policy(self, policy, expected_revision, accepted, expected_session_id=None):
        with self.lock:
            if not self.active or accepted is not True:
                raise ValueError('An active session and acceptance of the agreed rules are required')
            if not isinstance(expected_session_id, str) or expected_session_id != self.session:
                raise ValueError('The session changed; review the current session before saving rules')
            if type(expected_revision) is not int or expected_revision != self.policy['revision']:
                raise ValueError('Session rules changed; review the current revision before saving')
            updated = normalize_policy(policy, self.policy['revision'] + 1)
            self.store.append(self.session, 'session_policy', updated)
            self.policy = updated
            self.last_audit = 0  # Next poll retains a sample with the new interpretation.
            self._event('Session rules updated', f"Revision {updated['revision']}; phase: {updated['phase']}. Monitoring scopes are unchanged.", persist=False)
            return self.snapshot()

    def _sample(self, results):
        reviewed = apply_policy(results, self.policy)
        return {'score': score(reviewed), 'results': [r.json() for r in reviewed],
                'review_groups': review_groups(reviewed),
                'policy_revision': self.policy['revision'] if self.policy else None}

    def heartbeat(self):
        with self.lock:
            if self.active:
                self.last_seen = time.monotonic()
            return {"active": self.active}

    def watchdog(self, expected_session=...):
        with self.lock:
            if expected_session is not ... and self.session != expected_session:
                return
            if not self.active:
                return
            tick = time.monotonic()
            self._expire_measurements(tick, time.time())
            session = self.session
            reason = None
            if tick - self.last_seen > 15:
                reason = "Candidate dashboard disconnected or heartbeat expired"
            elif tick - self.start_time > 2 * 3600:
                reason = "Two-hour session limit reached; fresh consent is required"
        if reason:
            self.stop(reason, expected_session=session)

    def _expire_measurements(self, tick, wall):
        """Called under the engine lock, independently of potentially blocked scans."""
        scopes = {d.name: d.scope for d in self.detectors}
        results = copy.deepcopy(self.results)
        changed = False
        for result in results:
            clocks = self.sample_clocks.get(result.detector)
            if clocks is None or result.status not in ('available', 'partial'):
                continue
            scope = scopes[result.detector]
            deadline = 8 if scope in ('windows', 'gaze') else 25
            elapsed = max(tick - clocks[0], wall - clocks[1])
            inventory_expired = (scope == 'extensions' and self.context.get('extension_expires_tick') is not None
                                 and tick >= self.context['extension_expires_tick'])
            if elapsed <= deadline and not inventory_expired:
                continue
            result.status = 'waiting'
            result.detail = ('Measurements exceeded their freshness deadline; scheduling, suspension or clock changes may be involved. '
                             'Exact outage timing is unknown. Waiting for a fresh measurement.')
            result.metrics['freshness'] = 'expired'
            self.last_scans.pop(result.detector, None)
            if result.detector == 'GazeDetector':
                result.metrics['consistency'] = None
            self.coverage.observe(result, scope, tick, now(), self._coverage_event,
                                  boundary='detected_freshness_deadline')
            changed = True
        if changed:
            self.store.append(self.session, 'sample', self._sample(results))
            self.results = results

    def poll(self, expected_session=...):
        # Pin the whole operation, including watchdog checks, to one session.
        # A queued monitor call must never scan a replacement session while
        # its caller still attributes failures to the previous session.
        with self.lock:
            if expected_session is ...:
                expected_session = self.session
        self.watchdog(expected_session=expected_session)
        # A concurrent caller never queues behind a native scan.
        if not self.poll_lock.acquire(blocking=False):
            return self.snapshot()
        try:
            return self._poll(expected_session)
        finally:
            self.poll_lock.release()

    def _poll(self, expected_session):
        with self.lock:
            if self.session != expected_session:
                return self.snapshot()
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
        results, scanned, scan_clocks = [], {}, {}
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
                scanned[detector.name] = time.monotonic()
                scan_clocks[detector.name] = (scanned[detector.name], time.time())
            results.append(result)
        with self.lock:
            if not self.active or self.session != session:
                return self.snapshot()
            sampled_at, completed_tick = now(), time.monotonic()
            scopes = {d.name: d.scope for d in detectors}
            # A concurrent watchdog may have invalidated a cached sample.
            current = {r.detector: r for r in self.results}
            results = [current.get(r.detector, r) if r.detector not in scanned else r for r in results]
            # Never publish a browser result computed from superseded import data.
            inventory_changed = self.context != context and consent.get('extensions')
            if inventory_changed:
                scanned.pop('BrowserExtensionDetector', None)
                scan_clocks.pop('BrowserExtensionDetector', None)
                results = [Result(r.detector, 'waiting', 'Inventory changed during sampling; waiting for a fresh scan.')
                           if r.detector == 'BrowserExtensionDetector' and consent.get('extensions') else r for r in results]
            for result in results:
                if result.detector in scanned or (inventory_changed and result.detector == 'BrowserExtensionDetector'):
                    self.coverage.observe(result, scopes[result.detector], completed_tick,
                                          sampled_at, self._coverage_event)
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
            groups = review_groups(results)
            if groups != review_groups(self.results):
                self.store.append(self.session, 'source_groups', {'version': 1, 'groups': groups})
            gaze = next((r.metrics.get("consistency") for r in results if r.detector == "GazeDetector"), None)
            sample = self._sample(results)
            point = {"time": now(), "score": sample['score']["value"], "gaze": gaze}
            self.history.append(point)
            if tick - self.last_audit >= 10:
                self.store.append(self.session, "sample", sample)
                self.last_audit = tick
            self.last_scans.update(scanned)
            self.sample_clocks.update(scan_clocks)
            self.results, self.known, self.observed = results, set(new), new
            self._expire_measurements(completed_tick, time.time())
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            sample = self._sample(self.results)
            return {"session_id": self.session, "active": self.active, "stopping": self.stopping,
                    "cleanup_state": ("failed" if self.stop_result.done() else "in_progress")
                    if self.stopping else "complete" if self.stop_result else "idle",
                    "consent": self.consent,
                    "policy": copy.deepcopy(self.policy),
                    "coverage_gaps": self.coverage.snapshot(),
                    "time": now(), **sample,
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

    def stop(self, reason="Candidate stopped monitoring", expected_session=...):
        with self.lock:
            if expected_session is not ... and self.session != expected_session:
                return self.snapshot()
            if self.stop_result is not None:
                completion, owns_cleanup = self.stop_result, False
            elif not self.active:
                return self.snapshot()
            else:
                completion = self.stop_result = Future()
                owns_cleanup = True
                self.active = False
                self.stopping = True
                detectors = list(self.detectors)
        if not owns_cleanup:
            # Wait without the engine lock; every caller observes this session's
            # same cleanup outcome even if a new session starts immediately.
            return copy.deepcopy(completion.result())
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
                self.coverage.finish(time.monotonic(), now(), self._coverage_event)
                self.store.append(self.session, "sample", self._sample(self.results))
                for identity in sorted(self.known):
                    self.store.append(self.session, "signal_resolved", {
                        "signal_id": identity, "reason": "Monitoring stopped; observation tracking ended"})
                self.store.stop(self.session, reason)
                self._event("Monitoring stopped", reason, persist=False)
                self.context.clear()
                self.question_at = None
            if failures:
                raise RuntimeError("Device cleanup failed; close the desktop application")
            with self.lock:
                self.stopping = False
                result = self.snapshot()
                completion.set_result(result)
            return copy.deepcopy(result)
        except BaseException as error:
            with self.lock:
                # Storage failures also block restart: no successful terminal
                # audit was established. Always release concurrent stop callers.
                self.stopping = True
                completion.set_exception(error)
            raise

    def import_extensions(self, entries, digest=None):
        with self.lock:
            if not self.active or not self.consent.get("extensions"):
                raise ValueError("Active session and extension-inventory consent are required")
            from .inventory import prepare_inventory
            clean, metadata, expiry = prepare_inventory(entries, digest, self.session, time.monotonic(), now())
            checked = metadata['checksum_verified']
            detail = ("Candidate supplied an inventory with a matching content checksum; authenticity and completeness are unverified."
                      if checked else "Candidate supplied an inventory without a checksum; authenticity and completeness are unverified.")
            self.store.append(self.session, 'extension_inventory_imported', metadata)
            self._event("Extension inventory imported", detail, persist=False)
            self.context.update(extensions=clean, extension_inventory=metadata, extension_expires_tick=expiry)
            self.last_scans.pop("BrowserExtensionDetector", None)
            return {"imported": len(clean), "verified": checked, "checksum_verified": checked,
                    "browser_authenticated": False, "session_bound": metadata['session_bound']}

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
            self.stop_result = None
            self.policy = None
            self.coverage = CoverageTracker()
            self.timeline.clear()
            self.history.clear()
            return self.snapshot()
