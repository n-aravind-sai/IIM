"""Single-tenant reporting API reference. Explicit upload, independent key pinning.

Not the live desktop worker. Run behind a TLS reverse proxy for remote use.
One instance per tenant; do not expose the stdlib HTTP server publicly.
"""
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from worker.audit import verify, canonical


def make_server(host="127.0.0.1", port=8080, directory=None, write_token=None, read_token=None, trusted_keys=None, cleanup_interval=60):
    if not 0 < cleanup_interval <= 60:
        raise ValueError("cleanup_interval must be greater than zero and at most 60 seconds")
    write_token = write_token or os.environ.get("REPORT_WRITE_TOKEN", "")
    read_token = read_token or os.environ.get("REPORT_READ_TOKEN", "")
    trusted_keys = trusted_keys if trusted_keys is not None else json.loads(os.environ.get("REPORT_TRUSTED_KEYS", "[]"))
    if min(len(write_token),len(read_token))<32 or write_token==read_token or not trusted_keys:
        raise ValueError("Distinct read/write tokens (32+ characters) and pinned REPORT_TRUSTED_KEYS are required")
    folder=Path(directory or os.environ.get("REPORT_DATA_DIR",".reports"));folder.mkdir(parents=True,exist_ok=True)
    if os.name!='nt':folder.chmod(0o700)
    db=sqlite3.connect(folder/'reports.sqlite3',check_same_thread=False)
    db.executescript((Path(__file__).parent/'schema.sql').read_text())
    lock=threading.Lock();limits={}
    def prune_expired():
        with lock, db:
            db.execute('DELETE FROM reports WHERE expires_at <= ?', (time.time(),))
    prune_expired()  # Remove downtime-expired records before accepting requests.
    last_cleanup = time.monotonic()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,data):
            body=json.dumps(data).encode();self.send_response(code)
            self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def authorized(self,write=False):
            supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
            valid=hmac.compare_digest(supplied.encode(),write_token.encode()) or (not write and hmac.compare_digest(supplied.encode(),read_token.encode()))
            if not valid:self.reply(401,{'error':'Unauthorized'});return False
            current=time.time()
            with lock:
                # Bind a single tenant to a single credential scope, not untrusted IP headers.
                role='write' if hmac.compare_digest(supplied.encode(),write_token.encode()) else 'read'
                bucket=[t for t in limits.get(role,[]) if current-t<60]
                if len(bucket)>=120:self.reply(429,{'error':'Rate limit'});return False
                limits[role]=bucket+[current]
            return True
        def do_POST(self):
            if not self.authorized(write=True):return
            if self.path!='/v1/reports':self.reply(404,{'error':'Not found'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=8*1024*1024:raise ValueError('Body must be 1 byte to 8 MB')
                self.connection.settimeout(5)
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict) or payload.get('consent_to_upload') is not True:raise ValueError('Explicit upload consent is required')
                bundle=payload.get('bundle',{})
                if not isinstance(bundle,dict) or bundle.get('public_key') not in trusted_keys or not verify(bundle):raise ValueError('Audit signature or enrolled key is invalid')
                if bundle['manifest']['session']['status']=='active':raise ValueError('Stop the session before upload')
                if bundle['manifest']['session']['consent'].get('accepted') is not True:raise ValueError('Session consent is missing')
                identity=str(uuid.uuid4());expiry=time.time()+86400
                with lock,db:db.execute('INSERT INTO reports VALUES(?,?,?,?)',(identity,time.time(),expiry,canonical(bundle)))
                self.reply(201,{'id':identity,'expires_at':expiry})
            except (ValueError,KeyError,TypeError,json.JSONDecodeError) as error:self.reply(400,{'error':str(error)})
        def report_id(self):
            try:
                prefix='/v1/reports/'
                if not self.path.startswith(prefix):return None
                return str(uuid.UUID(self.path[len(prefix):]))
            except ValueError:return None
        def do_GET(self):
            if not self.authorized():return
            identity=self.report_id()
            with lock:row=db.execute('SELECT bundle_json FROM reports WHERE id=? AND expires_at > ?',(identity,time.time())).fetchone()
            if row:self.reply(200,json.loads(row[0]))
            else:self.reply(404,{'error':'Not found or expired'})
        def do_DELETE(self):
            if not self.authorized(write=True):return
            identity=self.report_id()
            if identity is None:self.reply(404,{'error':'Not found'});return
            with lock,db:db.execute('DELETE FROM reports WHERE id=?',(identity,))
            self.reply(200,{'deleted':True})
    class ReportServer(ThreadingHTTPServer):
        daemon_threads = False  # Join handlers before closing their database.
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            return connection, address
        def service_actions(self):
            nonlocal last_cleanup
            if time.monotonic() - last_cleanup >= cleanup_interval:
                prune_expired()
                last_cleanup = time.monotonic()
        def server_close(self):
            super().server_close()
            with lock:
                if not getattr(self, 'database_closed', False):
                    db.close()
                    self.database_closed = True
    server=ReportServer((host,port),Handler)
    return server


if __name__=='__main__':
    server=make_server(host=os.environ.get('REPORT_BIND','127.0.0.1'),port=int(os.environ.get('PORT','8080')))
    print('Reporting API started. No desktop monitoring is performed.',flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
