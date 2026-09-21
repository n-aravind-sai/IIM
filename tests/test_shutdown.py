import asyncio
import multiprocessing as mp
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from worker.engine import Engine, DISCLOSURE
from worker.models import Result
from worker.probes import NativeProbe
from worker.gaze import GazeDetector
from worker.server import Service

CONSENT = {'accepted': True, 'version': DISCLOSURE, 'processes': True, 'gaze': True}

class HungNative:
    name, scope = 'ProcessDetector', 'processes'
    def scan(self, context):
        while True:
            time.sleep(.1)

class ResponsiveNative:
    name, scope = 'ProcessDetector', 'processes'
    def __init__(self): self.calls = 0
    def scan(self, context):
        self.calls += 1
        return Result(self.name, 'partial', 'Fixture', metrics={'calls': self.calls})

class BlockingDetector:
    name, scope = 'ProcessDetector', 'processes'
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.closed = False
    def scan(self, context):
        self.entered.set()
        self.release.wait()
        return Result(self.name, 'partial', 'Late result')
    def close(self): self.closed = True

class CameraFixture:
    name, scope = 'GazeDetector', 'gaze'
    def __init__(self): self.closed = False
    def scan(self, context): return Result(self.name, 'partial', 'Camera fixture')
    def close(self): self.closed = True

class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.blocked, self.camera = BlockingDetector(), CameraFixture()
        self.engine = Engine(self.tmp.name, lambda: [self.camera, self.blocked])
        self.engine.start(CONSENT)
        self.poller = None
    def tearDown(self):
        self.blocked.release.set()
        if self.poller: self.poller.join(2)
        if self.engine.active: self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()
    def block(self):
        self.poller = threading.Thread(target=self.engine.poll, daemon=True)
        self.poller.start()
        self.assertTrue(self.blocked.entered.wait(2))
    def test_stop_and_heartbeat_do_not_wait_for_scan(self):
        self.block()
        started = time.monotonic()
        self.assertTrue(self.engine.heartbeat()['active'])
        state = self.engine.stop()
        self.assertLess(time.monotonic() - started, .5)
        self.assertFalse(state['active'])
        self.assertTrue(self.camera.closed)
        self.assertTrue(self.poller.is_alive())
        self.assertEqual(state['results'], [])
    def test_watchdog_runs_while_sampling_is_blocked(self):
        self.block()
        self.engine.last_seen = time.monotonic() - 16
        async def run():
            service = Service(self.engine, 'x'*32)
            task = asyncio.create_task(service.watchdog())
            try:
                for _ in range(100):
                    if not self.engine.active and self.camera.closed: break
                    await asyncio.sleep(.01)
                self.assertFalse(self.engine.active)
                self.assertTrue(self.camera.closed)
                self.assertTrue(self.poller.is_alive())
            finally:
                service.halt.set()
                await task
        asyncio.run(run())
    def test_old_results_do_not_enter_new_session(self):
        self.block()
        self.engine.stop()
        self.engine.factory = lambda: []
        new_session = self.engine.start(CONSENT)['session_id']
        self.blocked.release.set(); self.poller.join(2)
        self.assertEqual(self.engine.session, new_session)
        self.assertEqual(self.engine.results, [])
        self.assertNotIn('Late result', str(self.engine.export()))
    def test_one_cleanup_failure_does_not_skip_camera(self):
        self.engine.detectors.reverse()
        with patch.object(self.blocked, 'close', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError): self.engine.stop()
        self.assertTrue(self.camera.closed)
        with self.assertRaises(ValueError): self.engine.start(CONSENT)
    def test_stale_watchdog_cannot_stop_replacement_session(self):
        old = self.engine.session
        self.engine.stop(); self.engine.start(CONSENT)
        self.engine.stop('stale watchdog', expected_session=old)
        self.assertTrue(self.engine.active)

class SubprocessTests(unittest.TestCase):
    def test_production_registry_isolates_native_scopes(self):
        from worker.detectors import registry
        detectors = registry()
        self.assertEqual({d.scope for d in detectors if isinstance(d, NativeProbe)},
                         {'processes', 'windows', 'audio_devices', 'displays'})
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory)
            try:
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True})
                state = engine.poll()
                result = next(r for r in state['results'] if r['detector'] == 'ProcessDetector')
                self.assertEqual(result['status'], 'partial')
                process = next(d.process for d in engine.detectors if d.scope == 'processes')
                engine.stop()
                self.assertFalse(process.is_alive())
            finally:
                if engine.active: engine.stop()
                engine.store.db.close()

    def test_never_returning_native_probe_has_deadline_and_is_reaped(self):
        probe = NativeProbe(HungNative, timeout=.6)
        try:
            started = time.monotonic()
            result = probe.scan({})
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(result.status, 'error')
            self.assertIsNone(probe.process)
            self.assertTrue(probe.closed.is_set())
        finally: probe.close()
    def test_external_stop_reaps_stuck_child_and_releases_scan(self):
        probe = NativeProbe(HungNative, timeout=30)
        thread = threading.Thread(target=probe.scan, args=({},), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 3
            while probe.process is None and time.monotonic() < deadline: time.sleep(.01)
            with probe.lifecycle: process = probe.process
            self.assertIsNotNone(process)
            started = time.monotonic(); probe.close(); thread.join(1)
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertFalse(thread.is_alive())
            self.assertFalse(process.is_alive())
        finally: probe.close(); thread.join(2)
    def test_native_state_persists_between_polls(self):
        probe = NativeProbe(ResponsiveNative)
        try:
            self.assertEqual(probe.scan({}).metrics['calls'], 1)
            self.assertEqual(probe.scan({}).metrics['calls'], 2)
        finally: probe.close()
    def test_camera_closed_before_scan_cannot_start_later(self):
        camera = GazeDetector(); camera.close()
        self.assertEqual(camera.scan({}).status, 'disabled')
        self.assertIsNone(camera.process)
    def test_camera_cleanup_kills_a_real_stuck_process(self):
        parent, child = mp.get_context('spawn').Pipe()
        entered = mp.get_context('spawn').Event()
        process = mp.get_context('spawn').Process(target=stuck_camera, args=(entered,), daemon=True)
        process.start(); child.close()
        camera = GazeDetector(); camera.process, camera.pipe = process, parent
        try:
            self.assertTrue(entered.wait(3))
            camera.close()
            self.assertFalse(process.is_alive())
            self.assertIsNone(camera.pipe)
            self.assertEqual(camera.scan({}).status, 'disabled')
        finally:
            camera.close()


def stuck_camera(entered):
    entered.set()
    while True:
        time.sleep(.1)
