"""Explicit browser-development launcher. Not a production server."""
import asyncio
import json
import os
import secrets
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from worker.engine import Engine
from worker.server import Service


def make_dev_server(connection, bootstrap_secret, port=1420):
    """Create the development listener without starting native monitoring."""
    root = Path(__file__).resolve().parent.parent
    if not isinstance(bootstrap_secret, str) or len(bootstrap_secret) < 32:
        raise ValueError('A private bootstrap secret of at least 32 characters is required')
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root / "web"), **kwargs)
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.headers.get("Host") not in (f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"):
                self.send_error(403); return
            if urlsplit(self.path).path == "/bootstrap.json":
                supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
                if not secrets.compare_digest(supplied.encode(), bootstrap_secret.encode()):
                    self.send_error(403); return
                if self.headers.get("Sec-Fetch-Site") == "cross-site" or self.headers.get("Origin") not in (None,"http://127.0.0.1:1420","http://localhost:1420"):
                    self.send_error(403); return
                data=json.dumps(connection).encode()
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.send_header("Cache-Control","no-store")
                self.send_header("Content-Length",str(len(data)))
                self.end_headers(); self.wfile.write(data)
                return
            super().do_GET()
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


async def main():
    root = Path(__file__).resolve().parent.parent
    connection = {}
    service = Service(Engine(root / ".local-data"), secrets.token_urlsafe(32), dev=True)
    bootstrap_secret = os.environ.get('IIM_DEV_BOOTSTRAP_SECRET') or secrets.token_urlsafe(32)
    httpd = None
    def ready(info):
        nonlocal httpd
        connection.update(info)
        httpd = make_dev_server(connection, bootstrap_secret)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        from urllib.parse import quote
        print(f"Private development dashboard: http://127.0.0.1:1420/#bootstrap={quote(bootstrap_secret, safe='')} (Ctrl+C to stop)",flush=True)
    try:
        await service.run(ready)
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        service.engine.stop("Development launcher stopped")


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
