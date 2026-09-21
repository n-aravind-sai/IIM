import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from worker.audit import verify, canonical
from worker.engine import Engine, DISCLOSURE
from worker.models import Result, Signal
from worker.report import retained_observations, render_report

class BriefDetector:
    name, scope = 'OverlayDetector', 'windows'
    def __init__(self): self.signals = []
    def scan(self, context): return Result(self.name, 'partial', 'Fixture', copy.deepcopy(self.signals))
    def close(self): pass

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.detector = BriefDetector()
        self.engine = Engine(self.tmp.name, lambda: [self.detector])
        self.signal = Signal('brief', self.detector.name, 'Brief overlay fixture', .8, .5,
                             {'marker': 'UNIQUE-BRIEF-EVIDENCE'}, 'A transient observation.', 'An accessibility tool may match.')
        self.engine.start({'accepted': True, 'version': DISCLOSURE, 'windows': True})
        self.tick(100, [])
    def tearDown(self):
        self.engine.store.db.close(); self.tmp.cleanup()
    def tick(self, tick, signals):
        self.detector.signals = signals
        with patch('worker.engine.time.monotonic', return_value=tick):
            self.engine.last_seen = tick
            return self.engine.poll()
    def events(self):
        return [json.loads(e['payload_json']) for e in self.engine.export()['events']]
    def test_brief_observation_signed_before_live_export_and_retained_after_resolution(self):
        state = self.tick(102, [self.signal])
        self.assertEqual(len(state['results'][0]['signals']), 1)
        events = self.events()
        self.assertEqual(len([e for e in events if e['kind']=='sample']), 1)
        self.assertEqual(retained_observations(events)['brief']['evidence'], self.signal.evidence)
        self.tick(104, []); self.engine.stop()
        bundle = self.engine.export()
        self.assertTrue(verify(bundle, self.engine.store.public_key_base64))
        events = self.events()
        self.assertTrue(all(not r['signals'] for e in events if e['kind']=='sample' for r in e['data']['results']))
        self.assertEqual(len(retained_observations(events)), 1)
        self.assertEqual([e['data']['signal_id'] for e in events if e['kind']=='signal_resolved'], ['brief'])
        observed = next(e for e in events if e['kind']=='signal_observed')
        self.assertIn('time', observed)
        self.assertEqual(set(observed['data']['signal']), {'id','detector','title','confidence','weight','evidence','explanation','limitation'})
    def test_recurrence_and_changed_details_are_kept_without_duplicate_steady_events(self):
        self.tick(102, [self.signal]); self.tick(104, [self.signal]); self.tick(106, [])
        self.tick(108, [self.signal]); changed = copy.deepcopy(self.signal); changed.confidence = .7
        self.tick(110, [changed]); self.engine.stop()
        events = self.events()
        self.assertEqual(len([e for e in events if e['kind']=='signal_observed']), 3)
        self.assertEqual(len([e for e in events if e['kind']=='signal_resolved']), 2)
        self.assertEqual(len(retained_observations(events)), 1)
        self.assertEqual(retained_observations(events)['brief']['confidence'], .7)
    def test_failed_evidence_write_does_not_publish_signal(self):
        original = self.engine.store.append
        def append(session, kind, data):
            if kind == 'signal_observed': raise OSError('disk full')
            return original(session, kind, data)
        with patch.object(self.engine.store, 'append', side_effect=append):
            with self.assertRaises(OSError): self.tick(102, [self.signal])
        self.assertEqual(self.engine.snapshot()['results'][0]['signals'], [])
    def test_editing_or_removing_observation_breaks_signature(self):
        self.tick(102, [self.signal]); self.tick(104, [])
        bundle = self.engine.export()
        event = next(e for e in bundle['events'] if json.loads(e['payload_json'])['kind']=='signal_observed')
        event['payload_json'] = event['payload_json'].replace('UNIQUE-BRIEF-EVIDENCE', 'altered')
        self.assertFalse(verify(bundle))
        bundle = self.engine.export()
        bundle['events'] = [e for e in bundle['events'] if json.loads(e['payload_json'])['kind']!='signal_observed']
        self.assertFalse(verify(bundle))
    def test_sample_only_legacy_reports_keep_their_observations(self):
        from dataclasses import asdict
        events = [{'kind':'sample', 'data':{'results':[{'signals':[asdict(self.signal)]}]}}]
        self.assertEqual(retained_observations(events)['brief']['evidence'], self.signal.evidence)
    @unittest.skipUnless(shutil.which('pdftotext'), 'Poppler required for rendered PDF text extraction')
    def test_actual_pdf_includes_evidence_missing_from_all_samples(self):
        self.tick(102, [self.signal]); self.tick(104, []); self.engine.stop()
        path = Path(self.tmp.name) / 'brief.pdf'
        path.write_bytes(render_report(self.engine.export()))
        text = subprocess.check_output(['pdftotext', str(path), '-'], text=True)
        self.assertIn('UNIQUE-BRIEF-EVIDENCE', text)
        self.assertIn(self.signal.limitation, text)
        self.assertIn('First observed:', text)
        self.assertNotIn('No matching observations were retained', text)
