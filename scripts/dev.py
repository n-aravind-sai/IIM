"""Explicit browser-development launcher. Not a production server."""
import asyncio
import json
import secrets
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from worker.engine import Engine
from worker.server import Service


async def main():
    root = Path(__file__).resolve().parent.parent
    connection = {}
    service = Service(Engine(root / ".local-data"), secrets.token_urlsafe(32), dev=True)
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root / "web"), **kwargs)
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.headers.get("Host") not in ("localhost:1420", "127.0.0.1:1420"):
                self.send_error(403); return
            if urlsplit(self.path).path == "/bootstrap.json":
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
    def ready(info):
        connection.update(info)
        httpd = ThreadingHTTPServer(("127.0.0.1",1420),Handler)
        threading.Thread(target=httpd.serve_forever,daemon=True).start()
        print("Development dashboard: http://127.0.0.1:1420 (Ctrl+C to stop)",flush=True)
    try:
        await service.run(ready)
    finally:
        service.engine.stop("Development launcher stopped")


if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
