import tempfile
import unittest
from pathlib import Path
from worker.engine import Engine, DISCLOSURE

class DisclosureTests(unittest.TestCase):
    def test_old_disclosure_cannot_authorize_expanded_camera_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            e=Engine(d,lambda:[])
            try:
                with self.assertRaises(ValueError):e.start({'accepted':True,'version':'iim-consent-1','gaze':True})
                state=e.start({'accepted':True,'version':DISCLOSURE,'gaze':True})
                self.assertEqual(state['consent']['version'],'iim-consent-2')
                self.assertTrue(e.export()['manifest']['session']['consent']['gaze'])
            finally:
                if e.active:e.stop()
                e.store.db.close()
    def test_ui_and_api_send_current_disclosure(self):
        self.assertIn(DISCLOSURE,Path('web/app.js').read_text())
        self.assertIn(DISCLOSURE,Path('docs/api.md').read_text())
    def test_camera_fields_and_preview_are_disclosed_before_consent(self):
        html=Path('web/index.html').read_text()
        consent=html.split('<dialog id="consent-dialog">')[1]
        for phrase in ['face count','multiple-face','lighting','calibration','eye-position','pre-flight']:
            self.assertIn(phrase,consent)
        self.assertIn('microphone level meter',html)
        self.assertNotIn('Only an experimental eye-position aggregate is retained',html)
