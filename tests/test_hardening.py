import json
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from worker.engine import Engine, DISCLOSURE
from worker.models import Result, Signal
from worker.policy import normalize_policy, apply_policy
from worker.detectors import BrowserExtensionDetector, VirtualDisplayDetector


class UnverifiedPolicyTests(unittest.TestCase):
    def test_candidate_cannot_approve_or_suppress_a_matching_observation(self):
        policy = normalize_policy({'allowed_apps': ['otter']})
        self.assertEqual(policy['approval_status'], 'unverified')
        raw = Result('ProcessDetector', 'partial', 'Fixture', [
            Signal('one', 'ProcessDetector', 'Match', .8, .5, {'process': 'otter'}, 'Observed', 'Not proof')])
        reviewed = apply_policy([raw], policy)[0].signals[0]
        self.assertEqual(reviewed.weight, .5)
        self.assertEqual(reviewed.evidence['session_policy']['disposition'], 'pending_review')
        for key in ('approval_status', 'approved_by', 'source'):
            with self.assertRaises(ValueError):
                normalize_policy({key: 'approved'})


class InventoryFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Engine(self.tmp.name, lambda: [BrowserExtensionDetector()])
        self.engine.start({'accepted': True, 'version': DISCLOSURE, 'extensions': True})

    def tearDown(self):
        self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()

    def inventory(self, **changes):
        from worker.inventory import bound_checksum
        data = {'format': 'iim.extensions.v3', 'session_id': self.engine.session,
                'exported_at': datetime.now(timezone.utc).isoformat(),
                'browser': 'Chrome', 'profile': 'Interview profile', 'extensions': []}
        data.update(changes)
        data['digest'] = bound_checksum(data)
        return data

    def test_legacy_inventory_does_not_claim_current_session_coverage(self):
        self.engine.import_extensions([])
        state = self.engine.poll()
        self.assertNotIn(state['results'][0]['status'], ('partial', 'available'))
        self.assertTrue(state['coverage_gaps'])

    def test_bound_inventory_recovers_then_expires_using_local_clock(self):
        self.engine.import_extensions(self.inventory())
        self.assertEqual(self.engine.poll()['results'][0]['status'], 'partial')
        with patch('worker.detectors.time.monotonic', return_value=time.monotonic() + 301):
            result = BrowserExtensionDetector().scan(self.engine.context)
        self.assertEqual(result.status, 'waiting')
        self.assertEqual(result.metrics['freshness'], 'expired')

    def test_wrong_session_future_stale_and_modified_metadata_rejected(self):
        data = self.inventory()
        data['profile'] = 'Changed'
        cases = [data, self.inventory(session_id='another-session'),
                 self.inventory(exported_at=(datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()),
                 self.inventory(exported_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat())]
        before = self.engine.export()
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.engine.import_extensions(data)
        self.assertEqual(self.engine.export(), before)

    def test_failed_import_audit_does_not_publish_new_inventory(self):
        with patch.object(self.engine.store, 'append', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.engine.import_extensions(self.inventory())
        self.assertNotIn('extensions', self.engine.context)

    def test_import_during_scan_does_not_publish_superseded_coverage(self):
        self.engine.import_extensions(self.inventory())
        detector = self.engine.detectors[0]
        scan = detector.scan
        def replace_while_scanning(context):
            result = scan(context)
            self.engine.import_extensions([])
            return result
        with patch.object(detector, 'scan', side_effect=replace_while_scanning):
            state = self.engine.poll()
        self.assertEqual(state['results'][0]['status'], 'waiting')
        self.assertTrue(state['coverage_gaps'])
        self.assertIsNone(state['score']['value'])
        self.assertNotIn(detector.name, self.engine.last_scans)



class DisplayPolicyTests(unittest.TestCase):
    def test_unusable_or_expired_display_count_cannot_assess_current_limit(self):
        for status,freshness in [('waiting','expired'),('error',None),('disabled',None),
                                 ('unsupported',None),('partial','expired')]:
            for count in (1,2):
                with self.subTest(status=status,freshness=freshness,count=count):
                    raw=Result('VirtualDisplayDetector',status,'Count unavailable',
                               metrics={'active_desktop_monitors':count,'freshness':freshness})
                    reviewed=apply_policy([raw],normalize_policy({'max_displays':1}))[0]
                    self.assertEqual(reviewed.metrics['declared_limit_assessment'],'unknown')
                    self.assertEqual(reviewed.signals,[])
                    self.assertEqual(raw.metrics['active_desktop_monitors'],count)
                    self.assertNotIn('declared_limit_assessment',raw.metrics)

    def test_expired_display_assessment_is_signed_unknown_then_recovers(self):
        class Probe:
            name,scope='VirtualDisplayDetector','displays'
            count=2
            def scan(self,context):
                return Result(self.name,'partial','Fixture',metrics={'active_desktop_monitors':self.count})
            def close(self): pass
        probe=Probe()
        with tempfile.TemporaryDirectory() as directory:
            engine=Engine(directory,lambda:[probe])
            try:
                with patch('worker.engine.time.monotonic',return_value=100):
                    engine.start({'accepted':True,'version':DISCLOSURE,'displays':True},{'max_displays':1})
                    self.assertEqual(engine.poll()['results'][0]['metrics']['declared_limit_assessment'],
                                     'exceeds_declared_limit')
                with patch('worker.engine.time.monotonic',return_value=126):
                    engine.heartbeat()
                    engine.watchdog()
                    result=engine.snapshot()['results'][0]
                    self.assertEqual(result['metrics']['declared_limit_assessment'],'unknown')
                    self.assertEqual(result['signals'],[])
                    events=[json.loads(e['payload_json']) for e in engine.export()['events']]
                    samples=[e['data'] for e in events if e['kind']=='sample']
                    self.assertEqual(samples[-1]['results'][0]['metrics']['declared_limit_assessment'],'unknown')
                    self.assertEqual(samples[0]['results'][0]['metrics']['declared_limit_assessment'],
                                     'exceeds_declared_limit')
                    probe.count=1
                    current=engine.poll()['results'][0]
                    self.assertEqual(current['metrics']['declared_limit_assessment'],'no_observed_excess')
            finally:
                engine.stop()
                engine.store.db.close()

    def test_adapters_are_not_reported_as_monitors_and_declared_limit_is_review_only(self):
        with patch('platform.system', return_value='Windows'), \
                patch('worker.detectors.native.displays', return_value=[{'label': 'GPU', 'virtual_hint': False}]), \
                patch('worker.detectors.native.display_topology', return_value={
                    'active_desktop_monitors': 2, 'physical_monitor_count': None, 'source': 'fixture'}):
            result = VirtualDisplayDetector().scan({})
        self.assertNotIn('active_displays', result.metrics)
        self.assertEqual(result.metrics['adapter_count'], 1)
        reviewed = apply_policy([result], normalize_policy({'max_displays': 1}))[0]
        self.assertEqual(reviewed.metrics['declared_limit_assessment'], 'exceeds_declared_limit')
        self.assertEqual(reviewed.signals[-1].weight, 0)

    def test_macos_display_inventory_is_not_labelled_as_windows_adapters(self):
        with patch('platform.system', return_value='Darwin'), \
                patch('worker.detectors.native.displays', return_value=[{'label': 'External display', 'virtual_hint': None}]), \
                patch('worker.detectors.native.display_topology', side_effect=NotImplementedError):
            result = VirtualDisplayDetector().scan({})
        self.assertIsNone(result.metrics['adapter_count'])
        self.assertIsNone(result.metrics['active_desktop_monitors'])

    def test_unknown_topology_is_not_treated_as_within_limit(self):
        raw = Result('VirtualDisplayDetector', 'partial', 'Adapters only', metrics={'adapter_count': 1})
        result = apply_policy([raw], normalize_policy({'max_displays': 1}))[0]
        self.assertEqual(result.metrics['declared_limit_assessment'], 'unknown')


class FreshnessTests(unittest.TestCase):
    def test_wall_clock_discontinuity_forces_a_new_scan_before_recovery(self):
        class Probe:
            name, scope = 'ProcessDetector', 'processes'
            calls = 0
            def scan(self, context):
                self.calls += 1
                return Result(self.name, 'partial', 'Fixture')
            def close(self): pass
        probe = Probe()
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [probe])
            try:
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True})
                engine.poll()
                with patch('worker.engine.time.time', return_value=time.time() + 60):
                    engine.watchdog()
                    self.assertIsNone(engine.snapshot()['score']['value'])
                    engine.poll()
                self.assertEqual(probe.calls, 2, 'A cached result must not close a freshness gap')
                self.assertEqual(engine.snapshot()['coverage_gaps'], [])
            finally:
                engine.stop()
                engine.store.db.close()

    def test_watchdog_marks_stale_observations_unknown_before_heartbeat_stop(self):
        class Probe:
            name, scope = 'ProcessDetector', 'processes'
            def scan(self, context): return Result(self.name, 'partial', 'Fixture')
            def close(self): pass
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(directory, lambda: [Probe()])
            try:
                engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True})
                engine.poll()
                with patch('worker.engine.time.monotonic', return_value=time.monotonic() + 40):
                    engine.heartbeat()
                    engine.watchdog()
                state = engine.snapshot()
                self.assertTrue(state['active'])
                self.assertIsNone(state['score']['value'])
                self.assertTrue(state['coverage_gaps'])
                events = [json.loads(e['payload_json']) for e in engine.export()['events']]
                self.assertTrue(any(e['kind'] == 'coverage_gap_opened' and e['data']['status'] == 'waiting' for e in events))
            finally:
                engine.stop()
                engine.store.db.close()
