"""Camera metadata must distinguish live capture from usable measurements."""
import copy
import unittest
from unittest.mock import patch

from worker.coverage import CoverageTracker
from worker.gaze import GazeDetector, aggregate
from worker.models import Result, score


class LiveCameraProcess:
    def is_alive(self):
        return True


class MeasurementQualityTests(unittest.TestCase):
    def test_historical_eye_samples_do_not_hide_current_unusable_frame(self):
        result = aggregate([.5] * 100, .5, current_usable=False)
        self.assertIsNone(result['consistency'])
        self.assertEqual(result['quality'], 'insufficient')

    def test_buffered_camera_data_uses_capture_time_not_receive_time(self):
        from unittest.mock import Mock
        self.camera.pipe = Mock()
        self.camera.pipe.poll.side_effect = [True, False]
        self.camera.pipe.recv.return_value = {'consistency': 80, 'quality': 'experimental',
                                              'calibrated': True, '_captured_tick': 90}
        with patch.object(self.camera, '_fail', return_value=Result(self.camera.name, 'error', 'Stale')):
            self.assertEqual(self.camera.scan({}).status, 'error')

    def setUp(self):
        self.camera = GazeDetector()
        self.camera.process = LiveCameraProcess()
        self.camera.pipe = None
        self.camera.started_at = 90
        self.camera.last_update = 100
        self.clock = patch("worker.gaze.time.monotonic", return_value=100)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def scan(self, **metadata):
        self.camera.latest = metadata
        return self.camera.scan({})

    def test_live_camera_with_insufficient_eye_measurements_remains_waiting(self):
        cases = {
            "calibrating": {"quality": "calibrating", "calibrated": False,
                            "consistency": None, "valid_samples": 18, "faces_count": 1},
            "no_face": {"quality": "insufficient", "calibrated": True,
                        "consistency": None, "valid_samples": 0, "faces_count": 0},
            "no_eye_samples": {"quality": "insufficient", "calibrated": True,
                               "consistency": None, "valid_samples": 0, "faces_count": 1},
        }
        for name, metadata in cases.items():
            with self.subTest(condition=name):
                result = self.scan(**metadata)
                self.assertEqual(result.status, "waiting")
                self.assertEqual(result.metrics, metadata)
                self.assertFalse(self.camera.closed)

    def test_waiting_for_eye_measurements_preserves_unscored_multiple_face_observation(self):
        result = self.scan(quality="insufficient", calibrated=False, consistency=None,
                           valid_samples=0, faces_count=2, secondary_person=True)
        self.assertEqual(len(result.signals), 1)
        self.assertEqual(result.signals[0].weight, 0)
        self.assertEqual(result.signals[0].evidence["faces_detected"], 2)
        self.assertIsNone(score([result])["value"])
        self.assertEqual(result.status, "waiting")

    def test_calibrated_experimental_consistency_is_partial_coverage(self):
        result = self.scan(quality="experimental", calibrated=True, consistency=80,
                           valid_samples=25, faces_count=1, secondary_person=False)
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.metrics["consistency"], 80)
        self.assertEqual(result.signals, [])
        self.assertIsNone(score([result])["value"])

    def test_coverage_gap_closes_only_when_usable_eye_measurement_arrives(self):
        tracker = CoverageTracker()
        events = []

        def emit(kind, data):
            events.append((kind, copy.deepcopy(data)))

        tracker.observe(Result(self.camera.name, "waiting", "Waiting for first measurement"),
                        "gaze", 90, "2026-09-28T00:00:00Z", emit,
                        boundary="session_start")
        original_gap = tracker.snapshot()[0]["gap_id"]
        waiting = self.scan(quality="insufficient", calibrated=False, consistency=None,
                            valid_samples=0, faces_count=0)
        tracker.observe(waiting, "gaze", 100, "2026-09-28T00:00:10Z", emit)
        self.assertEqual(len(tracker.snapshot()), 1)
        self.assertEqual(tracker.snapshot()[0]["gap_id"], original_gap)
        self.assertFalse(any(kind == "coverage_gap_closed" for kind, _ in events))
        usable = self.scan(quality="experimental", calibrated=True, consistency=80,
                           valid_samples=25, faces_count=1)
        tracker.observe(usable, "gaze", 110, "2026-09-28T00:00:20Z", emit)
        self.assertEqual(tracker.snapshot(), [])
        closed = [data for kind, data in events if kind == "coverage_gap_closed"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["gap_id"], original_gap)
        self.assertEqual(closed[0]["duration_seconds"], 20)
        self.assertEqual(closed[0]["end_reason"], "measurements_resumed")
