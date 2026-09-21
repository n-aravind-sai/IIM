import copy
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from worker.audit import AuditStore, verify, canonical, digest
from worker.engine import Engine, DISCLOSURE
from worker.models import Result, Signal, score, CAPS
from worker.detectors import OverlayDetector, ProcessDetector
from worker.gaze import aggregate


class FakeDetector:
    name,scope='ProcessDetector','processes'
    def __init__(self):self.calls=0;self.closed=False
    def scan(self,context):self.calls+=1;return Result(self.name,'partial','Fixture')
    def close(self):self.closed=True


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.fake=FakeDetector()
        self.engine=Engine(self.tmp.name,lambda:[self.fake])
        self.consent={'accepted':True,'version':DISCLOSURE,'processes':True}
    def tearDown(self):
        self.engine.store.db.close();self.tmp.cleanup()
    def test_no_observations_without_consent(self):
        self.engine.poll();self.assertEqual(self.fake.calls,0)
        for consent in ({}, {'accepted':False,'version':DISCLOSURE}, {'accepted':True,'version':'stale'}):
            with self.assertRaises(ValueError):self.engine.start(consent)
        self.assertEqual(self.fake.calls,0)
    def test_disabled_scope_never_scanned(self):
        self.engine.start({'accepted':True,'version':DISCLOSURE,'windows':True});self.engine.poll()
        self.assertEqual(self.fake.calls,0)
    def test_stop_prevents_future_scans(self):
        self.engine.start(self.consent);self.engine.poll();self.engine.stop();self.engine.poll()
        self.assertEqual(self.fake.calls,1);self.assertTrue(self.fake.closed)
    def test_expired_heartbeat_stops_before_scan(self):
        self.engine.start(self.consent);self.engine.last_seen=time.monotonic()-16;self.engine.poll()
        self.assertFalse(self.engine.active);self.assertEqual(self.fake.calls,0)
    def test_second_session_requires_fresh_consent(self):
        self.engine.start(self.consent);self.engine.stop()
        with self.assertRaises(ValueError):self.engine.start({'accepted':False})
    def test_delete_cascades(self):
        self.engine.start(self.consent);self.engine.poll();self.engine.stop();self.engine.delete()
        for table in ('sessions','events','seals'):
            self.assertEqual(self.engine.store.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
    def test_no_delete_during_active_session(self):
        self.engine.start(self.consent)
        with self.assertRaises(ValueError):self.engine.delete()
    def test_gaze_is_excluded_and_unknown_is_not_clean(self):
        gaze=Result('GazeDetector','partial','experimental',[Signal('a','GazeDetector','Drift',1,1,{},'','')])
        self.assertIsNone(score([gaze])['value'])
        base=Result('ProcessDetector','partial','')
        self.assertEqual(score([base,gaze])['value'],100)
        self.assertLess(score([base,gaze])['coverage'],100)
    def test_duplicate_signals_do_not_multiply_penalty(self):
        s=Signal('x','ProcessDetector','Name',.7,.5,{},'','')
        self.assertEqual(score([Result('ProcessDetector','partial','',[s])]),score([Result('ProcessDetector','partial','',[s]*20)]))
    def test_all_disabled_is_na(self):
        self.assertIsNone(score([Result('OverlayDetector','disabled','')])['value'])
    def test_score_badges(self):
        self.assertEqual(score([])['badge'], 'INSUFFICIENT_COVERAGE')
        base = Result('ProcessDetector', 'partial', '')
        self.assertEqual(score([base])['badge'], 'PARTIAL_COVERAGE')
        sig = Signal('x', 'ProcessDetector', 'Name', .7, .5, {}, '', '')
        self.assertEqual(score([Result('ProcessDetector', 'partial', '', [sig])])['badge'], 'OBSERVATIONS_FOR_REVIEW')
        all_avail = [Result(d, 'available', '') for d in CAPS if d != 'GazeDetector']
        self.assertEqual(score(all_avail)['badge'], 'STANDARD_BASELINE')
    def test_extension_import_requires_separate_consent(self):
        self.engine.start(self.consent)
        with self.assertRaises(ValueError):self.engine.import_extensions([])
    def test_notes_are_bounded(self):
        self.engine.start(self.consent)
        for note in ('','x'*501,42):
            with self.assertRaises(ValueError):self.engine.note(note)
    def test_gaze_low_quality_is_missing_not_zero(self):
        self.assertIsNone(aggregate([None]*20,.5)['consistency'])
        self.assertEqual(aggregate([.5]*20,.5)['consistency'],100)
    def test_failed_affinity_query_is_not_flagged(self):
        row={'id':'1','pid':8,'topmost':False,'layered':False,'clickthrough':False,'alpha':None,'affinity':None}
        with patch('worker.native.windows',return_value=[row]):
            r=OverlayDetector().scan({})
        self.assertEqual(r.signals,[]);self.assertFalse(r.metrics['capture_affinity_observable'])
    def test_capture_flag_is_reported_with_limitation(self):
        row={'id':'1','pid':8,'topmost':False,'layered':True,'clickthrough':False,'alpha':.9,'affinity':17}
        with patch('worker.native.windows',return_value=[row]):r=OverlayDetector().scan({})
        self.assertEqual(len(r.signals),1);self.assertIn('legitimate',r.signals[0].limitation)
    def test_process_metadata_minimized(self):
        with patch('worker.native.processes',return_value=[{'pid':99,'name':'Cluely.exe'},{'pid':12,'name':'private-personal-tool'}]):r=ProcessDetector().scan({})
        serialized=canonical(r.json())
        self.assertNotIn('private-personal-tool',serialized);self.assertNotIn('pid',serialized)
        self.assertEqual(r.signals[0].evidence['process'],'cluely')
    def test_renamed_process_detected_via_metadata(self):
        mock_procs = [
            {'pid': 101, 'name': 'system_helper.exe', 'metadata': {'OriginalFilename': 'cluely.exe', 'FileDescription': 'Helper'}},
            {'pid': 102, 'name': 'notes.exe', 'metadata': {'OriginalFilename': 'notes.exe', 'ProductName': 'Interview Coder Pro'}},
            {'pid': 103, 'name': 'innocent.exe', 'metadata': {'OriginalFilename': 'innocent.exe', 'FileDescription': 'Safe tool'}}
        ]
        with patch('worker.native.processes', return_value=mock_procs):
            r = ProcessDetector().scan({})
        self.assertEqual(len(r.signals), 2)
        titles = {s.title for s in r.signals}
        self.assertIn("Renamed application matches a review rule", titles)
        self.assertIn("Application metadata matches a review rule", titles)
        serialized = canonical(r.json())
        self.assertNotIn("innocent", serialized)
        self.assertNotIn("103", serialized)
    def test_secondary_person_detection(self):
        from worker.gaze import GazeDetector
        g = GazeDetector()
        g.latest = {"consistency": 85, "quality": "experimental", "secondary_person": True, "faces_count": 2}
        g.last_update = time.monotonic()
        g.process = unittest.mock.MagicMock()
        g.process.is_alive.return_value = True
        g.pipe = unittest.mock.MagicMock()
        g.pipe.poll.return_value = False
        res = g.scan({})
        self.assertEqual(len(res.signals), 1)
        self.assertEqual(res.signals[0].title, "Multiple faces observed in camera frame")
        self.assertEqual(res.signals[0].weight, 0.0)
        s = score([res, Result('ProcessDetector', 'available', '')])
        self.assertEqual(s['value'], 100)

    def test_probe_error_is_explicit(self):
        self.engine.start(self.consent)
        with patch.object(self.fake,'scan',side_effect=PermissionError('private pathname')):state=self.engine.poll()
        self.assertEqual(state['results'][0]['status'],'error');self.assertIsNone(state['score']['value'])
        self.assertNotIn('private pathname',canonical(state))
    def test_manual_timing_is_not_scored(self):
        self.engine.start(self.consent);self.engine.poll();before=self.engine.snapshot()['score']
        self.engine.mark('question_end');self.engine.mark('answer_start')
        self.assertEqual(before,self.engine.snapshot()['score'])
    def test_snapshot_and_attestation(self):
        with self.assertRaises(ValueError):
            self.engine.attestation()
        self.engine.start(self.consent)
        snap = self.engine.snapshot()
        self.assertIn('public_key', snap)
        self.assertIn('head', snap)
        self.assertEqual(len(snap['head']), 64)
        self.assertEqual(snap['public_key'], self.engine.store.public_key_base64)
        att = self.engine.attestation()
        self.assertEqual(att['session_id'], self.engine.session)
        self.assertEqual(att['public_key'], snap['public_key'])
        self.assertEqual(att['head'], snap['head'])
        self.assertIn('<svg', att['svg'])
        self.assertIn('viewBox', att['svg'])
    def test_extension_digest_verification(self):
        import hashlib
        ext_consent = {'accepted': True, 'version': DISCLOSURE, 'extensions': True}
        self.engine.start(ext_consent)
        entries = [{'name': 'Grammarly', 'enabled': True}, {'name': 'AdBlock', 'enabled': False}]
        sorted_repr = json.dumps([['AdBlock', False], ['Grammarly', True]], separators=(',', ':'))
        valid_digest = hashlib.sha256(sorted_repr.encode()).hexdigest()
        res = self.engine.import_extensions(entries, valid_digest)
        self.assertEqual(res['imported'], 2)
        self.assertTrue(res['verified'])
        with self.assertRaises(ValueError):
            self.engine.import_extensions(entries, '0' * 64)
        bundle = {'format': 'iim.extensions.v1', 'digest': valid_digest, 'extensions': entries}
        res2 = self.engine.import_extensions(bundle)
        self.assertEqual(res2['imported'], 2)
        self.assertTrue(res2['verified'])
        res3 = self.engine.import_extensions(entries)
        self.assertEqual(res3['imported'], 2)
        self.assertFalse(res3['verified'])



class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=AuditStore(self.tmp.name)
        self.store.create('test-session',{'accepted':True});self.store.append('test-session','note',{'text':'Fixture'})
        self.store.stop('test-session','Done');self.bundle=self.store.export('test-session')
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def test_valid_signature_and_pinned_key(self):self.assertTrue(verify(self.bundle,self.bundle['public_key']))
    def test_changed_payload_fails(self):
        value=copy.deepcopy(self.bundle);value['events'][0]['payload_json']='{}';self.assertFalse(verify(value))
    def test_truncated_tail_fails(self):
        value=copy.deepcopy(self.bundle);value['events'].pop();self.assertFalse(verify(value))
    def test_reordering_fails(self):
        value=copy.deepcopy(self.bundle);value['events'].reverse();self.assertFalse(verify(value))
    def test_altered_consent_fails(self):
        value=copy.deepcopy(self.bundle);value['manifest']['session']['consent']['accepted']=False;self.assertFalse(verify(value))
    def test_wrong_expected_key_fails(self):self.assertFalse(verify(self.bundle,'a different pinned key'))
    def test_export_does_not_resign_tampered_db(self):
        with self.store.db:self.store.db.execute("UPDATE events SET payload_json='{}' WHERE sequence=1")
        with self.assertRaises(ValueError):self.store.export('test-session')
        with self.assertRaises(ValueError):self.store.append('test-session','note',{})
    def test_audit_store_head_and_public_key(self):
        self.assertTrue(len(self.store.public_key_base64) > 20)
        head = self.store.get_head('test-session')
        self.assertEqual(len(head), 64)
        self.assertEqual(self.store.get_head('nonexistent-session'), '0' * 64)
    def test_dpapi_key_protection_and_migration(self):
        import os
        from pathlib import Path
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            store1 = AuditStore(p)
            raw_disk = (p / "signing-key.bin").read_bytes()
            if os.name == 'nt':
                self.assertGreater(len(raw_disk), 32)
            pk1 = store1.public_key_base64
            store1.db.close()
            store2 = AuditStore(p)
            self.assertEqual(store2.public_key_base64, pk1)
            store2.db.close()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            legacy_key = Ed25519PrivateKey.generate()
            legacy_bytes = legacy_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
            expected_pk = legacy_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            expected_pk_b64 = base64.b64encode(expected_pk).decode()
            (p / "signing-key.bin").write_bytes(legacy_bytes)
            self.assertEqual(len((p / "signing-key.bin").read_bytes()), 32)
            migrated_store = AuditStore(p)
            self.assertEqual(migrated_store.public_key_base64, expected_pk_b64)
            if os.name == 'nt':
                self.assertGreater(len((p / "signing-key.bin").read_bytes()), 32)
            migrated_store.db.close()
            reopened = AuditStore(p)
            self.assertEqual(reopened.public_key_base64, expected_pk_b64)
            reopened.db.close()
    def test_rehashing_db_does_not_bypass_persisted_seal(self):
        previous='0'*64
        with self.store.db:
            rows=self.store.db.execute('SELECT * FROM events ORDER BY sequence').fetchall()
            for row in rows:
                payload='{}' if row['sequence']==1 else row['payload_json']
                hashed=digest('test-session',row['sequence'],previous,payload)
                self.store.db.execute('UPDATE events SET payload_json=?,previous_hash=?,event_hash=? WHERE sequence=?',(payload,previous,hashed,row['sequence']))
                previous=hashed
        with self.assertRaises(ValueError):self.store.export('test-session')


if __name__=='__main__':unittest.main()
