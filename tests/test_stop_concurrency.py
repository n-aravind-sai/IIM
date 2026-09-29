"""Regressions for overlapping stop requests during device cleanup."""
import asyncio
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from worker.engine import DISCLOSURE, Engine
from worker.models import Result
from worker.server import Service


CONSENT = {"accepted": True, "version": DISCLOSURE, "processes": True}


class GatedCleanupDetector:
    name, scope = "ProcessDetector", "processes"

    def __init__(self, fail=False):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail = fail
        self.close_count = 0

    def scan(self, context):
        return Result(self.name, "partial", "Fixture")

    def close(self):
        self.close_count += 1
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("Test did not release device cleanup")
        if self.fail:
            raise RuntimeError("Fixture device could not close")


class StopConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.detector = GatedCleanupDetector()
        self.engine = Engine(self.tmp.name, lambda: [self.detector])
        self.engine.start(CONSENT)
        self.pool = ThreadPoolExecutor(max_workers=2)

    def tearDown(self):
        self.detector.release.set()
        self.pool.shutdown(wait=True)
        if self.engine.active:
            self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()

    def stopped_events(self):
        payloads = [json.loads(event["payload_json"])
                    for event in self.engine.export()["events"]]
        return [event for event in payloads if event["kind"] == "stopped"]

    def overlapping_stops(self):
        first = self.pool.submit(self.engine.stop, "Candidate dashboard disconnected")
        self.assertTrue(self.detector.entered.wait(2), "Cleanup did not begin")
        second_started = threading.Event()
        second_finished = threading.Event()

        def second_stop():
            second_started.set()
            try:
                return self.engine.stop("Desktop application closed")
            finally:
                second_finished.set()

        second = self.pool.submit(second_stop)
        self.assertTrue(second_started.wait(2), "Second stop did not begin")
        return first, second, second_finished

    def test_overlapping_stops_wait_for_one_cleanup_and_one_final_audit_event(self):
        first, second, second_finished = self.overlapping_stops()
        try:
            self.assertFalse(second_finished.wait(.2),
                             "An overlapping stop must wait until cleanup completes")
        finally:
            self.detector.release.set()
        first_state, second_state = first.result(2), second.result(2)
        self.assertFalse(first_state["active"])
        self.assertFalse(second_state["active"])
        self.assertEqual(first_state["head"], second_state["head"])
        self.assertEqual(self.detector.close_count, 1)
        self.assertEqual(len(self.stopped_events()), 1)
        self.assertEqual(self.stopped_events()[0]["data"]["reason"],
                         "Candidate dashboard disconnected")
        self.assertTrue(self.engine.start(CONSENT)["active"])

    def test_overlapping_stops_report_cleanup_failure_and_block_restart(self):
        self.detector.fail = True
        first, second, second_finished = self.overlapping_stops()
        try:
            self.assertFalse(second_finished.wait(.2),
                             "Cleanup failure is unknown until device cleanup completes")
        finally:
            self.detector.release.set()
        for request in (first, second):
            with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
                request.result(2)
        self.assertFalse(self.engine.active)
        self.assertEqual(self.detector.close_count, 1)
        events = self.stopped_events()
        self.assertEqual(len(events), 1)
        self.assertIn("cleanup failed for: ProcessDetector", events[0]["data"]["reason"])
        with self.assertRaises(ValueError):
            self.engine.start(CONSENT)

    def test_stop_after_deletion_does_not_return_deleted_session_data(self):
        self.detector.release.set()
        self.engine.stop()
        self.engine.delete()
        state = self.engine.stop()
        self.assertIsNone(state["session_id"])
        self.assertEqual(state["timeline"], [])
        self.assertEqual(state["consent"], {})


class DisconnectingSocket:
    async def recv(self):
        return json.dumps({"token": "x" * 32})

    async def send(self, message):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class LocalServerFixture:
    """Replace only socket binding; run the real service lifecycle."""
    sockets = []

    def __init__(self):
        self.sockets = [self]

    def getsockname(self):
        return ("127.0.0.1", 12345)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class ServiceStopConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_audit_failure_still_waits_for_background_task_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [])
            engine.start(CONSENT)
            service = Service(engine, "x" * 32)
            ready = asyncio.get_running_loop().create_future()
            monitor_started = asyncio.Event()
            release_monitor = asyncio.Event()
            monitor_finished = asyncio.Event()
            background_tasks = []

            async def finishing_monitor():
                background_tasks.append(asyncio.current_task())
                monitor_started.set()
                try:
                    await service.halt.wait()
                    await release_monitor.wait()
                finally:
                    monitor_finished.set()

            run = None
            try:
                with patch("worker.server.serve", return_value=LocalServerFixture()), \
                        patch.object(service, "monitor", finishing_monitor), \
                        patch.object(engine.store, "stop", side_effect=OSError("Audit disk unavailable")):
                    run = asyncio.create_task(service.run(ready.set_result))
                    await asyncio.wait_for(ready, 2)
                    await asyncio.wait_for(monitor_started.wait(), 2)
                    service.halt.set()
                    done, _ = await asyncio.wait([run], timeout=.2)
                    self.assertFalse(done, "Audit failure abandoned a running background task")
                    release_monitor.set()
                    with self.assertRaisesRegex(OSError, "Audit disk unavailable"):
                        await asyncio.wait_for(run, 2)
                    self.assertTrue(monitor_finished.is_set())
                    with self.assertRaises(ValueError):
                        engine.start(CONSENT)
            finally:
                service.halt.set()
                release_monitor.set()
                await asyncio.gather(*background_tasks, return_exceptions=True)
                if run is not None:
                    await asyncio.gather(run, return_exceptions=True)
                engine.store.db.close()

    async def test_service_shutdown_joins_disconnect_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            detector = GatedCleanupDetector()
            engine = Engine(directory, lambda: [detector])
            engine.start(CONSENT)
            service = Service(engine, "x" * 32)
            ready = asyncio.get_running_loop().create_future()
            tasks = []
            try:
                with patch("worker.server.serve", return_value=LocalServerFixture()):
                    run = asyncio.create_task(service.run(ready.set_result))
                    tasks.append(run)
                    await asyncio.wait_for(ready, 2)
                    disconnected = asyncio.create_task(service.handle(DisconnectingSocket()))
                    tasks.append(disconnected)
                    self.assertTrue(await asyncio.to_thread(detector.entered.wait, 2))
                    service.halt.set()
                    # A failed second stop previously escaped Service.run while the
                    # disconnect handler was still closing the same device.
                    done, _ = await asyncio.wait([run], timeout=.2)
                    self.assertFalse(done, "Service exited before device cleanup completed")
                    detector.release.set()
                    await asyncio.wait_for(asyncio.gather(*tasks), 2)
                self.assertEqual(detector.close_count, 1)
                self.assertFalse(engine.active)
                payloads = [json.loads(event["payload_json"])
                            for event in engine.export()["events"]]
                self.assertEqual(sum(event["kind"] == "stopped" for event in payloads), 1)
            finally:
                service.halt.set()
                detector.release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
                engine.store.db.close()
