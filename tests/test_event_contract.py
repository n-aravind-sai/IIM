import copy
import json
import tempfile
import unittest
from pathlib import Path

from worker.audit import AuditStore, verify
from worker.report import retained_coverage_gaps


class EventContractTests(unittest.TestCase):
    def test_new_events_have_stable_session_sequence_identity_and_run_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            store = AuditStore(folder)
            try:
                store.create('fixture', {'accepted': True})
                store.append('fixture', 'timeline', {'title': 'Context'})
                first = store.export('fixture')
                self.assertEqual(first, store.export('fixture'))
                payloads = [json.loads(e['payload_json']) for e in first['events']]
                for index, event in enumerate(payloads, 1):
                    self.assertEqual(event['event_version'], 1)
                    self.assertEqual(event['event_id'], f'fixture:{index}')
                    self.assertEqual(event['session_id'], 'fixture')
                    self.assertEqual(event['sequence'], index)
                    self.assertGreaterEqual(event['monotonic_ms'], 0)
                self.assertEqual(payloads[0]['run_id'], payloads[1]['run_id'])
                self.assertLessEqual(payloads[0]['monotonic_ms'], payloads[1]['monotonic_ms'])
                self.assertTrue(verify(first))
                changed = copy.deepcopy(first)
                changed['events'][1]['payload_json'] = changed['events'][1]['payload_json'].replace('fixture:2', 'fixture:1')
                self.assertFalse(verify(changed))
            finally:
                store.db.close()

    def test_restart_records_unknown_interruption_and_closes_existing_gap_without_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            store = AuditStore(folder)
            store.create('interrupted', {'accepted': True, 'processes': True})
            store.append('interrupted', 'coverage_gap_opened', {
                'version': 1, 'gap_id': 'fixture-gap', 'detector': 'ProcessDetector',
                'scope': 'processes', 'status': 'error', 'detail': 'Unavailable',
                'started_at': '2026-01-01T00:00:00+00:00', 'last_usable_at': None,
                'ended_at': None, 'duration_seconds': None, 'end_reason': None,
                'boundary': 'observed_at_poll'})
            old_bundle = store.export('interrupted')
            last_time = json.loads(old_bundle['events'][-1]['payload_json'])['time']
            store.db.close()
            resumed = AuditStore(folder)
            try:
                bundle = resumed.export('interrupted')
                events = [json.loads(e['payload_json']) for e in bundle['events']]
                interruption = next(e for e in events if e['kind'] == 'interrupted')
                self.assertEqual(interruption['data']['last_recorded_at'], last_time)
                self.assertIsNone(interruption['data']['duration_seconds'])
                self.assertEqual(interruption['data']['boundary'], 'detected_on_restart')
                self.assertNotEqual(events[0]['run_id'], interruption['run_id'])
                gap = retained_coverage_gaps(events)[0]
                self.assertEqual(gap['end_reason'], 'worker_interrupted')
                self.assertIsNotNone(gap['ended_at'])
                self.assertIsNone(gap['duration_seconds'])
                self.assertTrue(verify(bundle))
            finally:
                resumed.db.close()

    def test_existing_sample_audit_remains_verifiable(self):
        sample = Path(__file__).resolve().parents[1] / 'output' / 'sample-audit.json'
        self.assertTrue(verify(json.loads(sample.read_text(encoding='utf-8'))))
