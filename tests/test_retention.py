from contextlib import closing
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from cloud.server import make_server

class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'reports.sqlite3'
        self.token='w'*40;self.read='r'*40;self.thread=None;self.server=None
    def tearDown(self):
        if self.thread:
            self.server.shutdown();self.thread.join(2)
        if self.server:self.server.server_close()
        self.tmp.cleanup()
    def make(self,interval=60):
        self.server=make_server(port=0,directory=self.tmp.name,write_token=self.token,read_token=self.read,trusted_keys=['fixture'],cleanup_interval=interval)
    def insert(self,identity,expiry):
        with closing(sqlite3.connect(self.path)) as db, db:db.execute('INSERT INTO reports VALUES(?,?,?,?)',(identity,time.time(),expiry,'{}'))
    def ids(self):
        with closing(sqlite3.connect(self.path)) as db:return {r[0] for r in db.execute('SELECT id FROM reports')}
    def serve(self):
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.01),daemon=True);self.thread.start()
    def test_startup_removes_expired_rows_without_a_request(self):
        self.make();self.insert('expired',time.time()-1);self.insert('fresh',time.time()+3600)
        self.server.server_close();self.make()
        self.assertEqual(self.ids(),{'fresh'})
    def test_idle_expiry_deletes_rows_without_any_http_traffic(self):
        self.make(.03);self.insert('expires',time.time()+.08);self.insert('fresh',time.time()+3600);self.serve()
        deadline=time.monotonic()+2
        while 'expires' in self.ids() and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(self.ids(),{'fresh'})
    def test_read_cannot_return_expired_row_before_sweep(self):
        self.make(60);identity='00000000-0000-0000-0000-000000000001'
        self.insert(identity,time.time()-1);self.serve()
        url=f'http://127.0.0.1:{self.server.server_port}/v1/reports/{identity}'
        with self.assertRaises(HTTPError) as error:urlopen(Request(url,headers={'Authorization':'Bearer '+self.read}),timeout=2)
        self.assertEqual(error.exception.code,404)
        self.assertIn(identity,self.ids())  # Read denial did not rely on a sweep.
    def test_interval_validation(self):
        for interval in (0,-1,61):
            with self.assertRaises(ValueError):self.make(interval)
    def test_close_is_idempotent(self):
        self.make();self.server.server_close();self.server.server_close()
        self.assertTrue(self.server.database_closed)
