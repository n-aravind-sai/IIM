import json
import secrets
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from worker.audit import AuditStore
from worker.report import render_report
from cloud.server import make_server


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=AuditStore(self.tmp.name+'/local')
        self.store.create('sample',{'accepted':True,'processes':True});self.store.stop('sample','Finished')
        self.bundle=self.store.export('sample');self.write=secrets.token_urlsafe(32);self.read=secrets.token_urlsafe(32)
        self.server=make_server(port=0,directory=self.tmp.name+'/cloud',write_token=self.write,read_token=self.read,trusted_keys=[self.bundle['public_key']])
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.store.db.close();self.tmp.cleanup()
    def request(self,path,method='GET',data=None,token=None):
        req=Request(self.base+path,method=method,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+(token or self.write)})
        try:
            with urlopen(req,timeout=3) as response:return response.status,json.loads(response.read())
        except HTTPError as e:return e.code,json.loads(e.read())
    def test_pdf_is_generated_from_verified_bundle(self):
        self.assertTrue(render_report(self.bundle).startswith(b'%PDF-'))
        self.bundle['signature']='broken'
        with self.assertRaises(ValueError):render_report(self.bundle)
    def test_pdf_preserves_unicode_characters(self):
        self.store.create('unicode-session', {'accepted': True, 'processes': True})
        self.store.append('unicode-session', 'timeline', {'time': '2026-09-19T00:00:00Z', 'title': 'Candidate context', 'detail': 'René Müller agreed to use café terminal'})
        self.store.stop('unicode-session', 'Finished')
        bundle = self.store.export('unicode-session')
        pdf_bytes = render_report(bundle)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertNotIn(b'Ren\\xe9 M\\xfcller', pdf_bytes)
    def test_upload_requires_explicit_consent(self):
        status,_=self.request('/v1/reports','POST',{'bundle':self.bundle})
        self.assertEqual(status,400)
    def test_unknown_key_denied(self):
        self.bundle['public_key']='untrusted'
        status,_=self.request('/v1/reports','POST',{'bundle':self.bundle,'consent_to_upload':True})
        self.assertEqual(status,400)
    def test_read_token_cannot_upload(self):
        status,_=self.request('/v1/reports','POST',{'bundle':self.bundle,'consent_to_upload':True},self.read)
        self.assertEqual(status,401)
    def test_create_read_delete_report(self):
        status,data=self.request('/v1/reports','POST',{'bundle':self.bundle,'consent_to_upload':True})
        self.assertEqual(status,201);path='/v1/reports/'+data['id']
        status,bundle=self.request(path,token=self.read);self.assertEqual(status,200);self.assertEqual(bundle,self.bundle)
        self.assertEqual(self.request(path,'DELETE',token=self.read)[0],401)
        self.assertEqual(self.request(path,'DELETE')[0],200);self.assertEqual(self.request(path)[0],404)


if __name__=='__main__':unittest.main()
