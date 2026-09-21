import json
import tempfile
import unittest
from unittest.mock import patch
from worker.engine import Engine, DISCLOSURE
from worker.models import Result
from worker.detectors import AudioCaptureDetector, ProcessDetector, VirtualDisplayDetector
from worker.policy import validate_policy, apply_policy
from worker.audit import verify

class SessionEnhancementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Engine(self.tmp.name, lambda: [])
    def tearDown(self):
        self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()
    def start(self, focus=True, **policy):
        return self.engine.start({'accepted': True, 'version': DISCLOSURE, 'processes': True,
                                  'audio_devices': True, 'focus_events': focus}, policy)
    def events(self):
        return [json.loads(e['payload_json']) for e in self.engine.export()['events']]
    def test_policy_is_recorded_and_invalid_values_rejected_before_session(self):
        for value in ({'max_displays':True}, {'max_displays':0}, {'phase':'unknown'},
                      {'allowed_apps':['/private/app']}, {'unexpected':1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.start(**value)
        self.start(allowed_apps=[' OBS64.exe '], max_displays=2)
        self.assertEqual(self.engine.export()['manifest']['session']['consent']['policy']['allowed_apps'], ['obs64'])
        self.assertTrue(verify(self.engine.export()))
    def test_old_consent_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.start({'accepted':True,'version':'iim-consent-2','processes':True})
    def test_focus_requires_consent_and_current_session(self):
        self.start(focus=False)
        with self.assertRaises(ValueError):self.engine.focus_event(self.engine.session,1,True)
        self.engine.stop();self.start()
        with self.assertRaises(ValueError):self.engine.focus_event('stale-session',1,True)
        with self.assertRaises(ValueError):self.engine.focus_event(self.engine.session,True,True)
    def test_focus_deduplicates_and_measures_on_worker_clock(self):
        self.start()
        sid=self.engine.session
        with patch('worker.engine.time.monotonic',return_value=100):
            self.engine.focus_event(sid,1,True)
            self.engine.focus_event(sid,2,True)
        with patch('worker.engine.time.monotonic',return_value=107.5):
            self.assertFalse(self.engine.focus_event(sid,1,False)['accepted'])
            self.engine.focus_event(sid,3,False)
        focus=[e for e in self.events() if e['kind']=='timeline' and e['data']['title'].startswith('Dashboard focus')]
        self.assertEqual(len(focus),2)
        self.assertIn('7.5s',focus[-1]['data']['detail'])
    def test_stop_closes_away_interval_without_claiming_return(self):
        self.start();self.engine.focus_event(self.engine.session,1,True);self.engine.stop()
        self.assertTrue(any(e['data'].get('title')=='Focus interval incomplete' for e in self.events()))
    def test_coverage_recovery_and_device_counts_are_retained(self):
        class Probe:
            name,scope='AudioCaptureDetector','audio_devices'
            status,count='error',1
            def scan(self,context):return Result(self.name,self.status,'fixture',metrics={'input_count':self.count})
            def close(self):pass
        probe=Probe();self.engine.factory=lambda:[probe]
        self.start();self.engine.poll()
        probe.status='partial';self.engine.last_scans.clear();self.engine.poll()
        probe.count=2;self.engine.last_scans.clear();self.engine.poll()
        details=[e['data'].get('detail','') for e in self.events()]
        self.assertTrue(any('Unavailable interval:' in x for x in details))
        self.assertTrue(any('1 → 2' in x for x in details))
    def test_audio_hardware_is_unweighted_and_virtual_names_match(self):
        with patch('worker.detectors.native.audio_devices',return_value=[{'name':'Stereo Mix (Realtek)'}]):
            result=AudioCaptureDetector().scan({})
            self.assertEqual(result.signals,[])
            self.assertEqual(result.metrics['hardware_loopback_count'],1)
        for name in ['VoiceMeeter Output','VB-Audio Cable','OBS Virtual Audio','Krisp','SteelSeries Sonar','BlackHole']:
            with self.subTest(name=name),patch('worker.detectors.native.audio_devices',return_value=[{'name':name}]):
                self.assertEqual(len(AudioCaptureDetector().scan({}).signals),1)
    def test_permitted_process_remains_visible_without_weight(self):
        with patch('worker.detectors.native.processes',return_value=[{'name':'obs64.exe'}]):
            result=ProcessDetector().scan({})
        policy=validate_policy({'allowed_apps':['obs64']})
        apply_policy(result,policy);description=result.signals[0].limitation;apply_policy(result,policy)
        self.assertEqual(result.signals[0].weight,0)
        self.assertEqual(result.signals[0].limitation,description)
    def test_display_limit_is_unscored_and_idempotent(self):
        with patch('worker.detectors.native.displays',return_value=[{'virtual_hint':False}]*2):
            result=VirtualDisplayDetector().scan({})
        policy=validate_policy({'max_displays':1})
        apply_policy(result,policy);apply_policy(result,policy)
        self.assertEqual(len(result.signals),1)
        self.assertEqual(result.signals[0].weight,0)
