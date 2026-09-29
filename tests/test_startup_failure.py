"""Startup audit failures and stale monitor errors must never enable new scans."""
import asyncio
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from worker.engine import DISCLOSURE, Engine
from worker.models import Result
from worker.server import Service


CONSENT = {"accepted": True, "version": DISCLOSURE, "processes": True}


class CountingProbe:
    name, scope = "ProcessDetector", "processes"

    def __init__(self):
        self.scans = 0
        self.closed = False

    def scan(self, context):
        self.scans += 1
        return Result(self.name, "partial", "Fixture measurement")

    def close(self):
        self.closed = True


class StartupFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.probe = CountingProbe()
        self.engine = Engine(self.tmp.name, lambda: [self.probe])

    def tearDown(self):
        if self.engine.active:
            self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()

    def test_failed_new_consent_preserves_previous_completed_session(self):
        self.engine.start(CONSENT)
        previous = self.engine.stop()
        bundle = self.engine.export()
        append = self.engine.store.append

        def fail_consent(session, kind, data):
            if kind == "consent":
                raise OSError("Consent audit write failed")
            return append(session, kind, data)

        with patch.object(self.engine.store, "append", side_effect=fail_consent):
            with self.assertRaisesRegex(OSError, "Consent audit write failed"):
                self.engine.start({"accepted": True, "version": DISCLOSURE, "windows": True})
        current = self.engine.snapshot()
        self.assertEqual(current["session_id"], previous["session_id"])
        self.assertEqual(current["consent"], previous["consent"])
        self.assertEqual(current["head"], previous["head"])
        self.assertEqual(current["timeline"], previous["timeline"])
        self.assertFalse(current["active"])
        self.assertEqual(self.engine.export(), bundle)

    def test_failed_initial_gap_write_never_allows_device_scans(self):
        append = self.engine.store.append

        def fail_gap(session, kind, data):
            if kind == "coverage_gap_opened":
                raise OSError("Initial coverage audit write failed")
            return append(session, kind, data)

        with patch.object(self.engine.store, "append", side_effect=fail_gap):
            with self.assertRaisesRegex(OSError, "Initial coverage audit write failed"):
                self.engine.start(CONSENT)
        # The service's next monitor iteration still runs after the start RPC
        # reports its error. It must not activate a device from a failed start.
        self.engine.poll()
        self.assertEqual(self.probe.scans, 0)
        self.assertFalse(self.engine.active)
        self.assertTrue(self.probe.closed)


class RecordingSocket:
    def __init__(self):
        self.messages = []

    async def send(self, payload):
        self.messages.append(json.loads(payload))


class IterationHalt(asyncio.Event):
    """Observe the monitor reaching its between-iterations wait without sleeps."""
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()

    async def wait(self):
        self.waiting.set()
        return await super().wait()


class StaleMonitorFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_changed_before_poll_dispatch_cannot_hide_current_audit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [CountingProbe()])
            engine.start(CONSENT)
            service = Service(engine, "x" * 32)
            service.owner = RecordingSocket()
            dispatch_entered, release_dispatch = asyncio.Event(), asyncio.Event()
            to_thread = asyncio.to_thread
            first_dispatch = True
            failure_seen = False
            checkpoints = []

            async def gated_dispatch(function, *args, **kwargs):
                nonlocal first_dispatch
                if function == engine.poll and first_dispatch:
                    first_dispatch = False
                    dispatch_entered.set()
                    await release_dispatch.wait()
                return await to_thread(function, *args, **kwargs)

            class TwoIterationHalt(asyncio.Event):
                async def wait(self):
                    checkpoints.append((failure_seen, engine.active))
                    if len(checkpoints) == 1:
                        # Run one more iteration immediately: a valid fix may
                        # skip stale queued work before sampling this session.
                        raise asyncio.TimeoutError
                    self.set()
                    return True

            service.halt = TwoIterationHalt()
            monitor = None
            try:
                with patch("worker.server.asyncio.to_thread", side_effect=gated_dispatch):
                    monitor = asyncio.create_task(service.monitor())
                    await asyncio.wait_for(dispatch_entered.wait(), 2)
                    engine.stop()
                    replacement = engine.start(CONSENT)["session_id"]
                    append = engine.store.append

                    def fail_current_sample(session, kind, data):
                        nonlocal failure_seen
                        if session == replacement and kind == "sample" and not failure_seen:
                            failure_seen = True
                            raise OSError("Current session sample audit failed")
                        return append(session, kind, data)

                    with patch.object(engine.store, "append", side_effect=fail_current_sample):
                        release_dispatch.set()
                        await asyncio.wait_for(monitor, 3)
                self.assertTrue(failure_seen, "The replacement session was never sampled")
                self.assertFalse(any(failed and active for failed, active in checkpoints),
                                 "A current-session audit failure left monitoring active between polls")
                self.assertFalse(engine.active)
                self.assertTrue(all(probe.closed for probe in engine.detectors))
                self.assertTrue(any(message.get("type") == "fatal"
                                    for message in service.owner.messages))
            finally:
                release_dispatch.set()
                service.halt.set()
                if monitor is not None:
                    await asyncio.gather(monitor, return_exceptions=True)
                if engine.active:
                    engine.stop()
                engine.store.db.close()

    async def test_old_poll_failure_does_not_stop_or_publish_fatal_for_new_session(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [CountingProbe()])
            engine.start(CONSENT)
            service = Service(engine, "x" * 32)
            service.owner = RecordingSocket()
            service.halt = IterationHalt()
            entered, release = threading.Event(), threading.Event()

            def delayed_poll_error(**kwargs):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test did not release failed poll")
                raise OSError("Old session poll failed")

            monitor = None
            try:
                with patch.object(engine, "poll", side_effect=delayed_poll_error):
                    monitor = asyncio.create_task(service.monitor())
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    # The old worker error has not reached the service yet.
                    # The controller completes that session and starts another.
                    engine.stop()
                    replacement = engine.start(CONSENT)["session_id"]
                    release.set()
                    await asyncio.wait_for(service.halt.waiting.wait(), 2)
                    self.assertEqual(engine.session, replacement)
                    self.assertTrue(engine.active, "A stale poll failure stopped the replacement session")
                    self.assertFalse(any(message.get("type") == "fatal"
                                         for message in service.owner.messages),
                                     "A stale error was published to the healthy replacement session")
            finally:
                release.set()
                service.halt.set()
                if monitor is not None:
                    await asyncio.gather(monitor, return_exceptions=True)
                if engine.active:
                    engine.stop()
                engine.store.db.close()
