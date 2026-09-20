"""Reproduce a labelled synthetic PDF and signed audit without any monitoring."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from worker.audit import AuditStore, now
from worker.models import Result, score
from worker.detectors import signal
from worker.report import render_report

output=Path(__file__).resolve().parent.parent/'output';output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    store=AuditStore(directory)
    identity='synthetic-sample-not-a-real-interview'
    store.create(identity,{'accepted':True,'version':'iim-consent-1','synthetic':True,'processes':True,'windows':True,'displays':True,'gaze':False,'audio_devices':False,'extensions':False})
    observation=signal('OverlayDetector','sample','Overlay-style window observed',.8,.5,
        {'topmost':True,'layered':True,'source':'synthetic fixture'},
        'A synthetic window combines elevated stacking with overlay-like attributes.',
        'Captions, accessibility tools and meeting controls can produce the same properties.')
    results=[Result('OverlayDetector','partial','Synthetic metadata example; hidden GPU layers are unknown.',[observation]),
             Result('ProcessDetector','partial','Synthetic sample: no matching names.'),
             Result('AudioCaptureDetector','disabled','Not selected; audio is never recorded.'),
             Result('GazeDetector','disabled','Not selected; eye position is excluded from the index.'),
             Result('VirtualDisplayDetector','partial','Synthetic active-adapter metadata; hidden hardware is unknown.'),
             Result('BrowserExtensionDetector','disabled','No candidate inventory imported.')]
    store.append(identity,'sample',{'score':score(results),'results':[r.json() for r in results]})
    store.append(identity,'timeline',{'time':now(),'title':'Candidate context','detail':'SYNTHETIC EXAMPLE: Live captions were agreed before the interview.'})
    store.stop(identity,'Synthetic example completed. No person or device was monitored.')
    bundle=store.export(identity)
    (output/'sample-audit.json').write_text(json.dumps(bundle,indent=2))
    (output/'sample-report.pdf').write_bytes(render_report(bundle,synthetic=True))
    store.db.close()
print('Generated output/sample-report.pdf and output/sample-audit.json (synthetic only).')
