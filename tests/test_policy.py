import asyncio
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from worker.engine import Engine, DISCLOSURE
from worker.models import Result, Signal
from worker.server import Service
from worker.detectors import ProcessDetector
from worker.policy import apply_policy, normalize_policy
from worker.models import score
from worker.audit import verify


class ProcessIdentityPolicyTests(unittest.TestCase):
    def scan(self, name, metadata):
        with patch('worker.detectors.native.processes', return_value=[{'name': name, 'metadata': metadata}]):
            return ProcessDetector().scan({})

    def assert_identity_review(self, result, policy):
        before = copy.deepcopy(result.json())
        reviewed = apply_policy([result], normalize_policy(policy))[0]
        self.assertEqual(result.json(), before, 'Policy interpretation modified raw evidence')
        self.assertEqual(score([reviewed]), score([result]))
        for original, signal in zip(result.signals, reviewed.signals):
            self.assertEqual(signal.weight, original.weight)
            self.assertEqual(signal.confidence, original.confidence)
            self.assertEqual(signal.evidence['session_policy']['disposition'], 'identity_review')
            self.assertIn('not authenticated', signal.explanation)
        return reviewed

    def test_allowed_current_name_does_not_suppress_original_filename_match(self):
        raw = self.scan('code.exe', {'OriginalFilename': 'interviewcoder.exe'})
        self.assertEqual(len(raw.signals), 1)
        reviewed = self.assert_identity_review(raw, {'allowed_apps': ['CODE.EXE']})
        self.assertLess(score([reviewed])['value'], 100)

    def test_name_match_does_not_hide_different_original_filename_in_same_rule(self):
        raw = self.scan('interviewcoder.exe', {'OriginalFilename': 'cluely.exe'})
        self.assertEqual(len(raw.signals), 1)
        self.assertEqual(raw.signals[0].evidence.get('original_filename'), 'cluely')
        self.assert_identity_review(raw, {'allowed_apps': ['interviewcoder', 'cluely']})

    def test_product_metadata_match_is_not_automatically_exempted(self):
        raw = self.scan('code.exe', {'ProductName': 'InterviewCoder Desktop'})
        self.assertEqual(len(raw.signals), 1)
        self.assert_identity_review(raw, {'phase': 'coding', 'phase_apps': {'coding': ['code']}})

    def test_matching_original_name_requires_independent_approval(self):
        raw = self.scan('otter.exe', {'OriginalFilename': 'OTTER.EXE'})
        reviewed = apply_policy([raw], normalize_policy({'allowed_apps': ['otter']}))[0]
        self.assertEqual(score([reviewed]), score([raw]))
        self.assertEqual(reviewed.signals[0].evidence['session_policy']['disposition'], 'pending_review')

    def test_unmatched_metadata_does_not_create_identity_observations(self):
        raw = self.scan('code.exe', {'OriginalFilename': 'electron.exe', 'ProductName': 'Editor'})
        self.assertEqual(raw.signals, [])


class PolicyProbe:
    name, scope = 'ProcessDetector', 'processes'

    def scan(self, context):
        return Result(self.name, 'partial', 'Fixture', [
            Signal('app', self.name, 'Application match', .8, .5,
                   {'process': 'otter'}, 'Observed executable', 'Presence is not use.')])

    def close(self):
        pass


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Engine(self.tmp.name, lambda: [PolicyProbe()])
        self.consent = {'accepted': True, 'version': DISCLOSURE, 'processes': True}

    def tearDown(self):
        if self.engine.active:
            self.engine.stop()
        self.engine.store.db.close()
        self.tmp.cleanup()

    def test_declared_process_exception_retains_original_penalty(self):
        self.engine.start(self.consent, {'allowed_apps': ['OTTER.EXE']})
        state = self.engine.poll()
        self.assertEqual(state['score']['value'], 94)
        signal = state['results'][0]['signals'][0]
        self.assertEqual(signal['weight'], .5)
        self.assertEqual(signal['evidence']['session_policy']['disposition'], 'pending_review')
        self.assertEqual(state['policy']['allowed_apps'], ['otter'])
        events = [json.loads(e['payload_json']) for e in self.engine.export()['events']]
        original = next(e for e in events if e['kind'] == 'signal_observed')
        self.assertEqual(original['data']['signal']['weight'], .5)
        from worker.report import retained_policy_interpretations
        self.assertEqual(retained_policy_interpretations(events)[0]['policy']['disposition'], 'pending_review')
        self.assertLess(next(i for i,e in enumerate(events) if e['kind']=='session_policy'),
                        next(i for i,e in enumerate(events) if e['kind']=='signal_observed'))

    def test_phase_change_cannot_reduce_index_without_verified_approval(self):
        self.engine.start(self.consent, {'phase': 'coding', 'phase_apps': {'discussion': ['otter']}})
        self.assertEqual(self.engine.poll()['score']['value'], 94)
        updated = self.engine.update_policy({'phase': 'discussion', 'phase_apps': {'discussion': ['otter']}}, 1, True,
                                            expected_session_id=self.engine.session)
        self.assertEqual(updated['score']['value'], 94)
        self.assertEqual(updated['policy']['revision'], 2)
        self.assertTrue(updated['consent']['processes'])
        self.assertFalse(updated['consent']['gaze'])
        reverted = self.engine.update_policy({'phase': 'coding', 'phase_apps': {'discussion': ['otter']}}, 2, True,
                                             expected_session_id=self.engine.session)
        self.assertEqual(reverted['score']['value'], 94)

    def test_policy_change_requires_acceptance_and_current_revision(self):
        self.engine.start(self.consent)
        before = self.engine.export()
        for revision, accepted in [(1, False), (0, True), (True, True)]:
            with self.assertRaises(ValueError):
                self.engine.update_policy({'allowed_apps': ['otter']}, revision, accepted,
                                          expected_session_id=self.engine.session)
        self.assertEqual(self.engine.export(), before)

    def test_unknown_fields_paths_wildcards_and_invalid_limits_rejected_before_session(self):
        for policy in [{'gaze': True}, {'allowed_apps': ['*']}, {'allowed_apps': ['C:/app.exe']},
                       {'max_displays': True}, {'max_displays': 0}, {'phase': 'secret'},
                       {'phase_apps': {'secret': []}}, {'context': 'x' * 501}]:
            with self.subTest(policy=policy):
                with self.assertRaises(ValueError):
                    self.engine.start(self.consent, policy)
                self.assertFalse(self.engine.active)
                self.assertIsNone(self.engine.session)

    def test_exact_names_do_not_allow_similarly_named_processes(self):
        self.engine.start(self.consent, {'allowed_apps': ['ott']})
        self.assertEqual(self.engine.poll()['score']['value'], 94)

    def test_failed_policy_write_does_not_publish_new_policy(self):
        self.engine.start(self.consent)
        before = self.engine.snapshot()['policy']
        with patch.object(self.engine.store, 'append', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.engine.update_policy({'allowed_apps': ['otter']}, 1, True,
                                          expected_session_id=self.engine.session)
        self.assertEqual(self.engine.snapshot()['policy'], before)

    def test_new_session_does_not_inherit_allowed_tools(self):
        self.engine.start(self.consent, {'allowed_apps': ['otter']})
        self.engine.stop()
        self.engine.start(self.consent)
        self.assertEqual(self.engine.snapshot()['policy']['allowed_apps'], [])

    def test_snapshot_policy_cannot_be_mutated_by_caller(self):
        self.engine.start(self.consent, {'allowed_apps': ['otter']})
        self.engine.snapshot()['policy']['allowed_apps'].clear()
        self.assertEqual(self.engine.snapshot()['policy']['allowed_apps'], ['otter'])

    def test_policy_rpc_rejects_previous_session_even_when_revision_matches(self):
        previous = self.engine.start(self.consent)
        self.engine.stop()
        current = self.engine.start(self.consent)
        self.assertEqual(previous['policy']['revision'], current['policy']['revision'])
        before = self.engine.export()
        service = Service(self.engine, 'x' * 32)
        with self.assertRaisesRegex(ValueError, 'session'):
            asyncio.run(service.rpc('policy', {
                'policy': {'allowed_apps': ['otter']}, 'accepted': True,
                'expected_revision': previous['policy']['revision'],
                'expected_session_id': previous['session_id'],
            }))
        self.assertEqual(self.engine.export(), before)
        self.assertEqual(self.engine.snapshot()['policy'], current['policy'])

    def test_policy_rpc_requires_explicit_valid_session_identity(self):
        self.engine.start(self.consent)
        before = self.engine.export()
        service = Service(self.engine, 'x' * 32)
        for identity in (None, '', True, [], {}):
            with self.subTest(identity=identity):
                with self.assertRaisesRegex(ValueError, 'session'):
                    asyncio.run(service.rpc('policy', {
                        'policy': {'allowed_apps': ['otter']}, 'accepted': True,
                        'expected_revision': self.engine.policy['revision'],
                        **({'expected_session_id': identity} if identity is not None else {}),
                    }))
        self.assertEqual(self.engine.export(), before)

    def test_policy_rpc_accepts_current_session_and_revision(self):
        current = self.engine.start(self.consent)
        service = Service(self.engine, 'x' * 32)
        updated = asyncio.run(service.rpc('policy', {
            'policy': {'allowed_apps': ['otter']}, 'accepted': True,
            'expected_revision': current['policy']['revision'],
            'expected_session_id': current['session_id'],
        }))
        self.assertEqual(updated['policy']['revision'], 2)
        self.assertEqual(updated['policy']['allowed_apps'], ['otter'])

    def test_identity_review_survives_signed_export_and_pdf_without_rewriting_raw_evidence(self):
        from worker import report
        self.engine.factory = lambda: [ProcessDetector()]
        self.engine.start(self.consent, {'allowed_apps': ['code']})
        with patch('worker.detectors.native.processes', return_value=[
                {'name': 'code.exe', 'metadata': {'OriginalFilename': 'interviewcoder.exe'}}]):
            state = self.engine.poll()
        self.assertLess(state['score']['value'], 100)
        self.engine.stop()
        bundle = self.engine.export()
        self.assertTrue(verify(bundle))
        events = [json.loads(e['payload_json']) for e in bundle['events']]
        raw = next(e['data']['signal'] for e in events if e['kind'] == 'signal_observed')
        self.assertNotIn('session_policy', raw['evidence'])
        reviews = report.retained_policy_interpretations(events)
        self.assertEqual(len(reviews), 1, 'Repeated samples should not duplicate policy decisions')
        self.assertEqual(reviews[0]['policy']['disposition'], 'identity_review')
        self.assertEqual(reviews[0]['policy']['interpretation_version'], 3)
        self.assertEqual(reviews[0]['weight'], raw['weight'])
        self.assertEqual(report.retained_observations(events)[raw['id']]['evidence'], raw['evidence'])
        paragraphs = []
        paragraph = report.Paragraph

        def capture(text, style):
            paragraphs.append(text)
            return paragraph(text, style)

        with patch.object(report, 'Paragraph', side_effect=capture):
            pdf = report.render_report(bundle)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertTrue(any('identity review required' in text for text in paragraphs))
        self.assertTrue(any('interpretation 3' in text for text in paragraphs))

    def test_report_preserves_recorded_legacy_decision_and_policy_revisions(self):
        from worker.report import retained_policy_interpretations
        signal = {'id': 'app', 'title': 'Application match', 'weight': 0,
                  'evidence': {'process': 'code', 'original_filename': 'interviewcoder',
                               'session_policy': {'revision': 1, 'phase': 'coding', 'disposition': 'allowed'}}}
        legacy = {'kind': 'sample', 'time': 'first', 'data': {'results': [{'signals': [signal]}]}}
        current = copy.deepcopy(legacy)
        current['time'] = 'second'
        decision = current['data']['results'][0]['signals'][0]
        decision['weight'] = .7
        decision['evidence']['session_policy'].update(revision=2, interpretation_version=2, disposition='identity_review')
        reviews = retained_policy_interpretations([legacy, current, current])
        self.assertEqual([r['policy']['disposition'] for r in reviews], ['allowed', 'identity_review'])
        self.assertEqual([r['policy']['revision'] for r in reviews], [1, 2])
        self.assertEqual(legacy['data']['results'][0]['signals'][0]['weight'], 0)
