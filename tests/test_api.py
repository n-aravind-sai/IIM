import asyncio
import base64
import json
import secrets
import tempfile
import unittest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from worker.engine import Engine, DISCLOSURE
from worker.server import Service


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=Engine(self.tmp.name,lambda:[])
        self.service=Service(self.engine,secrets.token_urlsafe(32),True)
        self.ready=asyncio.get_running_loop().create_future()
        self.task=asyncio.create_task(self.service.run(self.ready.set_result))
        self.info=await self.ready
    async def asyncTearDown(self):
        self.service.halt.set();await self.task;self.engine.store.db.close();self.tmp.cleanup()
    async def authenticated(self):
        ws=await connect(self.info['endpoint'],origin='http://127.0.0.1:1420')
        await ws.send(json.dumps({'token':self.info['token']}))
        while json.loads(await ws.recv()).get('type')!='ready':pass
        return ws
    async def rpc(self,ws,op,args={}):
        await ws.send(json.dumps({'id':'test','op':op,'args':args}))
        while True:
            message=json.loads(await ws.recv())
            if message.get('type')=='response':return message
    async def test_wrong_token_denied(self):
        async with connect(self.info['endpoint'],origin='http://127.0.0.1:1420') as ws:
            await ws.send(json.dumps({'token':'wrong'}))
            with self.assertRaises(ConnectionClosed):await ws.recv()
        self.assertFalse(self.engine.active)
    async def test_untrusted_origin_denied(self):
        with self.assertRaises(InvalidStatus):await connect(self.info['endpoint'],origin='https://untrusted.invalid')
    async def test_missing_origin_denied(self):
        with self.assertRaises(InvalidStatus):await connect(self.info['endpoint'])
    async def test_api_requires_consent(self):
        ws=await self.authenticated();reply=await self.rpc(ws,'start',{'consent':{'accepted':False}})
        self.assertIn('error',reply);self.assertFalse(self.engine.active);await ws.close()
    async def test_disconnect_stops_active_session(self):
        ws=await self.authenticated();await self.rpc(ws,'start',{'consent':{'accepted':True,'version':DISCLOSURE,'processes':True}})
        self.assertTrue(self.engine.active);await ws.close()
        for _ in range(30):
            if not self.engine.active:break
            await asyncio.sleep(.01)
        self.assertFalse(self.engine.active)
    async def test_second_controller_is_denied(self):
        first=await self.authenticated()
        async with connect(self.info['endpoint'],origin='http://127.0.0.1:1420') as second:
            await second.send(json.dumps({'token':self.info['token']}))
            with self.assertRaises(ConnectionClosed):await second.recv()
        self.assertIsNotNone(self.service.owner);await first.close()
    async def test_export_pdf_via_rpc(self):
        ws=await self.authenticated()
        start=await self.rpc(ws,'start',{'consent':{'accepted':True,'version':DISCLOSURE,'processes':True}})
        self.assertTrue(self.engine.active)
        await self.rpc(ws,'note',{'text':'Test context note for PDF'})
        await self.rpc(ws,'stop')
        self.assertFalse(self.engine.active)
        reply=await self.rpc(ws,'export_pdf')
        self.assertIn('result',reply)
        result=reply['result']
        self.assertTrue(result['filename'].endswith('.pdf'))
        raw_pdf=base64.b64decode(result['base64'])
        self.assertTrue(raw_pdf.startswith(b'%PDF-'))
        await ws.close()
    async def test_attestation_via_rpc(self):
        ws=await self.authenticated()
        start=await self.rpc(ws,'start',{'consent':{'accepted':True,'version':DISCLOSURE,'processes':True}})
        self.assertTrue(self.engine.active)
        reply=await self.rpc(ws,'attestation')
        self.assertIn('result',reply)
        res=reply['result']
        self.assertEqual(res['session_id'],self.engine.session)
        self.assertEqual(res['public_key'],self.engine.store.public_key_base64)
        self.assertEqual(len(res['head']),64)
        self.assertIn('<svg',res['svg'])
        await ws.close()
    async def test_extensions_digest_via_rpc(self):
        import hashlib
        ws=await self.authenticated()
        await self.rpc(ws,'start',{'consent':{'accepted':True,'version':DISCLOSURE,'extensions':True}})
        entries=[{'name':'Tampermonkey','enabled':True}]
        canonical_repr=json.dumps([['Tampermonkey',True]],separators=(',',':'))
        digest=hashlib.sha256(canonical_repr.encode()).hexdigest()
        reply=await self.rpc(ws,'extensions',{'entries':entries,'digest':digest})
        self.assertIn('result',reply)
        self.assertTrue(reply['result']['verified'])
        tampered=await self.rpc(ws,'extensions',{'entries':entries,'digest':'bad-digest'})
        self.assertIn('error',tampered)
        await ws.close()



if __name__=='__main__':unittest.main()
