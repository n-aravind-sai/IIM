import json
import tempfile
import unittest
from unittest.mock import patch, Mock

from worker.detectors import ProcessDetector, OverlayDetector
from worker.engine import Engine, DISCLOSURE
from worker.models import Result, Signal
from worker.audit import verify


class SourceIdentityTests(unittest.TestCase):
    def test_native_instance_queries_release_handles_and_preserve_unknown(self):
        import ctypes
        from ctypes import wintypes as w
        from worker.native import process_creation_time
        api = Mock()
        api.OpenProcess.return_value = 77
        def times(handle, created, exited, kernel, user):
            self.assertEqual(handle, 77)
            value = ctypes.cast(created, ctypes.POINTER(w.FILETIME)).contents
            value.dwHighDateTime, value.dwLowDateTime = 2, 9
            return True
        api.GetProcessTimes.side_effect = times
        with patch('worker.native.platform.system', return_value='Windows'), \
                patch('worker.native.ctypes.WinDLL', return_value=api, create=True):
            self.assertEqual(process_creation_time(1234), (2 << 32) | 9)
            api.CloseHandle.assert_called_once_with(77)
            api.GetProcessTimes.side_effect = None
            api.GetProcessTimes.return_value = False
            self.assertIsNone(process_creation_time(1234))
            self.assertEqual(api.CloseHandle.call_count, 2)
            api.OpenProcess.return_value = None
            self.assertIsNone(process_creation_time(1234))
            self.assertEqual(api.CloseHandle.call_count, 2)
        with patch('worker.native.platform.system', return_value='Darwin'):
            self.assertIsNone(process_creation_time(1234))

    def test_source_tokens_are_session_scoped_and_pid_reuse_safe(self):
        from worker.correlation import source_for_process
        first = source_for_process(1234, 9999, b'a' * 32)
        self.assertEqual(first, source_for_process(1234, 9999, b'a' * 32))
        self.assertNotEqual(first, source_for_process(1234, 10000, b'a' * 32))
        self.assertNotEqual(first, source_for_process(1234, 9999, b'b' * 32))
        self.assertEqual(len(first['ref']), 64)
        for pid, created, key in [(0, 9999, b'a'*32), (1234, None, b'a'*32), (1234, 9999, None)]:
            self.assertIsNone(source_for_process(pid, created, key))

    def test_detectors_link_only_with_private_session_key_and_known_instance(self):
        rows = [{'name': 'otter.exe', 'pid': 1234, 'creation_time': 9999, 'metadata': {}}]
        windows = [{'id': 'handle', 'pid': 1234, 'topmost': True, 'layered': True,
                    'clickthrough': False, 'alpha': .5, 'affinity': None, 'creation_time': 9999}]
        with patch('worker.detectors.native.processes', return_value=rows), \
                patch('worker.detectors.native.windows', return_value=windows) as query:
            plain = OverlayDetector().scan({})
            query.assert_called_once_with(include_instance=False)
            self.assertNotIn('source', plain.signals[0].evidence)
            context = {'process_link_key': b'a' * 32}
            process = ProcessDetector().scan(context)
            overlay = OverlayDetector().scan(context)
            query.assert_called_with(include_instance=True)
            self.assertEqual(process.signals[0].evidence['source'], overlay.signals[0].evidence['source'])
            for result in (process, overlay):
                encoded = json.dumps(result.json())
                self.assertNotIn('1234', encoded)
                self.assertNotIn('9999', encoded)
                self.assertNotIn('handle', encoded)
                self.assertNotIn('process_link_key', encoded)
            windows[0]['creation_time'] = None
            self.assertNotIn('source', OverlayDetector().scan(context).signals[0].evidence)

    def test_engine_key_never_leaves_context_and_requires_both_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [])
            try:
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True})
                self.assertNotIn('process_link_key', engine.context)
                engine.stop()
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True, 'windows': True})
                key = engine.context['process_link_key']
                self.assertEqual(len(key), 32)
                self.assertNotIn('process_link_key', json.dumps(engine.snapshot()))
                self.assertNotIn('process_link_key', json.dumps(engine.export()))
                engine.stop()
                self.assertNotIn('process_link_key', engine.context)
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True, 'windows': True})
                self.assertNotEqual(key, engine.context['process_link_key'])
            finally:
                engine.stop()
                engine.store.db.close()

    def test_brief_source_group_is_signed_even_between_periodic_samples(self):
        source = {'kind': 'windows_process_instance', 'ref': 'a' * 64}
        class Probe:
            def __init__(self, name, scope): self.name, self.scope, self.signals = name, scope, []
            def scan(self, context): return Result(self.name, 'partial', 'Fixture', self.signals)
            def close(self): pass
        probes = [Probe('ProcessDetector', 'processes'), Probe('OverlayDetector', 'windows')]
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: probes)
            try:
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True, 'windows': True})
                engine.poll()
                for i, probe in enumerate(probes):
                    probe.signals = [Signal(str(i), probe.name, 'Fixture', .8, .5, {'source': source}, 'Observed', 'Not proof')]
                engine.last_scans.clear()
                state = engine.poll()
                self.assertEqual(len(state['review_groups']), 1)
                for probe in probes: probe.signals = []
                engine.last_scans.clear()
                engine.poll()
                engine.stop()
                bundle = engine.export()
                self.assertTrue(verify(bundle))
                events = [json.loads(row['payload_json']) for row in bundle['events']]
                transitions = [event['data']['groups'] for event in events if event['kind'] == 'source_groups']
                self.assertEqual(len(transitions), 2)
                self.assertEqual(transitions[0][0]['signal_ids'], ['0', '1'])
                self.assertEqual(transitions[1], [])
                from worker.report import retained_source_groups, render_report
                self.assertEqual(retained_source_groups(events)[0]['signal_ids'], ['0', '1'])
                self.assertTrue(render_report(bundle).startswith(b'%PDF'))
            finally:
                engine.stop()
                engine.store.db.close()
