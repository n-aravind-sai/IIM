import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from worker.audit import verify
from worker.engine import Engine, DISCLOSURE
from worker.models import Result


class CoverageProbe:
    name, scope = 'ProcessDetector', 'processes'

    def __init__(self):
        self.status = 'error'
        self.detail = 'Permission unavailable'

    def scan(self, context):
        return Result(self.name, self.status, self.detail)

    def close(self):
        pass


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.probe = CoverageProbe()
        self.engine = Engine(self.tmp.name, lambda: [self.probe])
        self.clock = patch('worker.engine.time.monotonic', return_value=100)
        self.tick = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True})

    def tearDown(self):
        if self.engine.active:
            self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()

    def poll(self, tick, status):
        self.tick.return_value = tick
        self.engine.heartbeat()
        self.probe.status = status
        return self.engine.poll()

    def events(self, kind):
        events = [json.loads(row['payload_json']) for row in self.engine.export()['events']]
        return [e['data'] for e in events if e['kind'] == kind]

    def test_waiting_error_recovery_is_one_signed_gap_with_monotonic_duration(self):
        initial = self.engine.snapshot()['coverage_gaps']
        self.assertEqual(len(initial), 1)
        self.assertEqual(initial[0]['status'], 'waiting')
        self.poll(102, 'error')
        self.poll(112, 'error')
        with patch('worker.engine.now', return_value='2000-01-01T00:00:00+00:00'):
            state = self.poll(122, 'partial')
        self.assertEqual(state['coverage_gaps'], [])
        self.assertEqual(len(self.events('coverage_gap_opened')), 1)
        self.assertEqual(len(self.events('coverage_gap_updated')), 1)
        closed = self.events('coverage_gap_closed')
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]['duration_seconds'], 22)
        self.assertEqual(closed[0]['end_reason'], 'measurements_resumed')
        self.assertEqual(closed[0]['gap_id'], initial[0]['gap_id'])
        self.assertTrue(verify(self.engine.export()))

    def test_recurrence_has_new_id_and_last_usable_sample(self):
        self.poll(100, 'partial')
        first = self.poll(110, 'error')['coverage_gaps'][0]
        self.assertIsNotNone(first['last_usable_at'])
        self.poll(120, 'partial')
        second = self.poll(130, 'unsupported')['coverage_gaps'][0]
        self.assertNotEqual(first['gap_id'], second['gap_id'])

    def test_stopping_ends_interval_without_claiming_recovery(self):
        self.poll(102, 'error')
        self.tick.return_value = 105
        state = self.engine.stop()
        self.assertEqual(state['coverage_gaps'], [])
        closed = self.events('coverage_gap_closed')[0]
        self.assertEqual(closed['end_reason'], 'monitoring_stopped')
        self.assertEqual(closed['duration_seconds'], 5)
        self.assertTrue(any(e['title'] == 'Coverage gap ended' for e in state['timeline']))

    def test_unselected_scope_never_opens_a_gap(self):
        self.engine.stop()
        self.engine.start({'accepted': True, 'version': DISCLOSURE, 'windows': True})
        self.assertEqual(self.engine.poll()['coverage_gaps'], [])
        self.assertEqual(self.events('coverage_gap_opened'), [])

    def test_failed_gap_write_is_not_published(self):
        self.poll(100, 'partial')
        original = self.engine.store.append

        def fail_gap(session, kind, data):
            if kind == 'coverage_gap_opened':
                raise OSError('disk full')
            return original(session, kind, data)

        with patch.object(self.engine.store, 'append', side_effect=fail_gap):
            with self.assertRaises(OSError):
                self.poll(110, 'error')
        self.assertEqual(self.engine.snapshot()['coverage_gaps'], [])

    def test_coverage_evidence_is_tamper_evident_and_retained_for_report(self):
        from worker.report import retained_coverage_gaps
        self.poll(110, 'error')
        bundle = self.engine.export()
        events = [json.loads(row['payload_json']) for row in bundle['events']]
        gaps = retained_coverage_gaps(events)
        self.assertEqual(len(gaps), 1)
        self.assertIsNone(gaps[0]['ended_at'])
        self.assertEqual(gaps[0]['detail'], 'Permission unavailable')
        changed = copy.deepcopy(bundle)
        row = next(e for e in changed['events'] if 'coverage_gap_opened' in e['payload_json'])
        row['payload_json'] = row['payload_json'].replace('ProcessDetector', 'OtherDetector')
        self.assertFalse(verify(changed))
        self.assertEqual(retained_coverage_gaps([]), [])
