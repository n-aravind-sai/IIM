import tempfile
import unittest
from unittest.mock import patch, Mock

from worker.engine import Engine, DISCLOSURE
from worker import detectors
from worker import native


class RemoteSessionTests(unittest.TestCase):
    def test_native_protocol_query_frees_buffer_and_rejects_short_responses(self):
        import ctypes
        from ctypes import wintypes as w
        value = ctypes.c_ushort(2)
        api = Mock()
        def reply(server, session, info, buffer, size):
            self.assertIsNone(server)
            self.assertEqual((session, info), (0xffffffff, 16))
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(value)
            ctypes.cast(size, ctypes.POINTER(w.DWORD))[0] = returned_size
            return True
        api.WTSQuerySessionInformationW.side_effect = reply
        with patch('worker.native.platform.system', return_value='Windows'), \
                patch('worker.native.ctypes.WinDLL', return_value=api, create=True):
            returned_size = 2
            self.assertEqual(native.remote_session()['protocol'], 'rdp')
            returned_size = 1
            with self.assertRaises(OSError): native.remote_session()
            self.assertEqual(api.WTSFreeMemory.call_count, 2)
            api.WTSQuerySessionInformationW.side_effect = None
            api.WTSQuerySessionInformationW.return_value = False
            with self.assertRaises(OSError): native.remote_session()

    def test_unsupported_platform_never_claims_console_or_monitor_count(self):
        with patch('worker.native.platform.system', return_value='Linux'):
            with self.assertRaises(NotImplementedError): native.remote_session()
            with self.assertRaises(NotImplementedError): native.display_topology()

    def test_protocol_is_observational_and_never_implies_third_party_control_absent(self):
        detector = detectors.RemoteSessionDetector()
        for protocol, status, signals in [('rdp', 'partial', 1), ('console', 'partial', 0), ('unknown', 'waiting', 0)]:
            with self.subTest(protocol=protocol), patch('worker.detectors.native.remote_session', return_value={
                    'protocol': protocol, 'scope': 'current_session', 'third_party_control': 'unknown'}):
                result = detector.scan({})
            self.assertEqual(result.status, status)
            self.assertEqual(len(result.signals), signals)
            self.assertEqual(result.metrics['third_party_control'], 'unknown')
            self.assertTrue(all(s.weight == 0 for s in result.signals))

    def test_remote_protocol_requires_its_own_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [detectors.RemoteSessionDetector()])
            try:
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True})
                with patch('worker.detectors.native.remote_session') as query:
                    self.assertEqual(engine.poll()['results'][0]['status'], 'disabled')
                    query.assert_not_called()
                engine.stop()
                engine.start({'accepted': True, 'version': DISCLOSURE, 'remote_sessions': True})
                with patch('worker.detectors.native.remote_session', side_effect=OSError('unavailable')):
                    self.assertEqual(engine.poll()['results'][0]['status'], 'error')
            finally:
                engine.stop()
                engine.store.db.close()
