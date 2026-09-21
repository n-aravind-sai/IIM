import unittest
from unittest.mock import MagicMock, patch
from worker.gaze import GazeDetector

class CameraTimeoutTests(unittest.TestCase):
    def camera(self):
        camera=GazeDetector()
        process=MagicMock();process.is_alive.side_effect=lambda:not process.terminate.called
        camera.process=process;camera.pipe=MagicMock();camera.pipe.poll.return_value=False
        camera.started_at=100
        return camera,process,camera.pipe
    def test_silent_live_camera_stops_at_startup_deadline(self):
        camera,process,pipe=self.camera()
        with patch('worker.gaze.time.monotonic',return_value=110):result=camera.scan({})
        self.assertEqual(result.status,'error');self.assertIn('10 seconds',result.detail)
        process.terminate.assert_called_once();pipe.close.assert_called_once()
        self.assertIsNone(camera.process);self.assertEqual(camera.scan({}).status,'error')
    def test_no_measurements_is_waiting_not_usable_coverage(self):
        camera,process,_=self.camera()
        with patch('worker.gaze.time.monotonic',return_value=109):result=camera.scan({})
        self.assertEqual(result.status,'waiting');process.terminate.assert_not_called()
    def test_first_measurement_removes_startup_deadline(self):
        camera,process,pipe=self.camera()
        pipe.poll.side_effect=[True,False];pipe.recv.return_value={'quality':'experimental','calibrated':True,'consistency':80}
        with patch('worker.gaze.time.monotonic',return_value=109):result=camera.scan({})
        self.assertEqual(result.status,'partial')
        pipe.poll.side_effect=None;pipe.poll.return_value=False
        with patch('worker.gaze.time.monotonic',return_value=111):result=camera.scan({})
        self.assertEqual(result.status,'partial');process.terminate.assert_not_called()
    def test_stale_measurements_stop_camera(self):
        camera,process,pipe=self.camera();camera.last_update=105
        with patch('worker.gaze.time.monotonic',return_value=109):result=camera.scan({})
        self.assertEqual(result.status,'error');self.assertIn('stale',result.detail)
        process.terminate.assert_called_once();pipe.close.assert_called_once()
    def test_worker_error_closes_devices(self):
        camera,process,pipe=self.camera();camera.latest={'error':'Camera unavailable'}
        self.assertEqual(camera.scan({}).status,'error');process.terminate.assert_called_once()
    def test_eof_releases_camera(self):
        camera,process,pipe=self.camera();pipe.poll.return_value=True;pipe.recv.side_effect=EOFError
        self.assertEqual(camera.scan({}).status,'error');pipe.close.assert_called_once()
    def test_spawn_failure_closes_both_pipe_ends(self):
        camera=GazeDetector();ctx=MagicMock();parent,child=MagicMock(),MagicMock();ctx.Pipe.return_value=(parent,child)
        ctx.Process.return_value.start.side_effect=OSError('private path')
        with patch('worker.gaze.mp.get_context',return_value=ctx):result=camera.scan({})
        self.assertEqual(result.status,'error');self.assertNotIn('private path',result.detail)
        parent.close.assert_called_once();child.close.assert_called_once()
        self.assertIsNone(camera.process)
