"""Loopback WebSocket RPC with exact origins and first-message authentication."""
import asyncio
import base64
import json
import secrets
import sys
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from .engine import Engine

DESKTOP_ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"]
DEV_ORIGINS = ["http://127.0.0.1:1420", "http://localhost:1420"]


class Service:
    def __init__(self, engine, token, dev=False):
        self.engine, self.token, self.dev = engine, token, dev
        self.owner = None
        self.authenticating = 0
        self.halt = asyncio.Event()
        self.send_lock = asyncio.Lock()

    async def send(self, ws, payload):
        async with self.send_lock:
            await asyncio.wait_for(ws.send(json.dumps(payload, allow_nan=False)), 3)

    async def rpc(self, op, args):
        if op == "snapshot":
            return self.engine.snapshot()
        if op == "start":
            return await asyncio.to_thread(self.engine.start, args.get("consent"), args.get("policy"))
        if op == "stop":
            return await asyncio.to_thread(self.engine.stop)
        if op == "heartbeat":
            return self.engine.heartbeat()
        if op == "focus":
            return await asyncio.to_thread(self.engine.focus_event, args.get("session_id"), args.get("sequence"), args.get("away"))
        if op == "note":
            return await asyncio.to_thread(self.engine.note, args.get("text"))
        if op == "mark":
            return await asyncio.to_thread(self.engine.mark, args.get("kind"))
        if op == "attestation":
            return await asyncio.to_thread(self.engine.attestation)
        if op == "extensions":
            return await asyncio.to_thread(self.engine.import_extensions, args.get("entries"), args.get("digest"))
        if op == "export_json":
            return await asyncio.to_thread(self.engine.export)
        if op == "export_pdf":
            from .report import render_report
            bundle = await asyncio.to_thread(self.engine.export)
            pdf = await asyncio.to_thread(render_report, bundle)
            return {"filename": f"interview-{bundle['manifest']['session']['id']}.pdf",
                    "base64": base64.b64encode(pdf).decode()}
        if op == "delete":
            return await asyncio.to_thread(self.engine.delete)
        raise ValueError("Unknown operation")

    async def handle(self, ws):
        if self.authenticating >= 4:
            await ws.close(1013, "Connection limit")
            return
        self.authenticating += 1
        authenticated = False
        try:
            message = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if not isinstance(message, dict) or not isinstance(message.get("token"), str) or not secrets.compare_digest(message["token"], self.token):
                await ws.close(1008, "Authentication failed")
                return
            if self.owner is not None:
                await ws.close(1008, "A candidate controller is already connected")
                return
            self.owner, authenticated = ws, True
            await self.send(ws, {"type": "ready", "snapshot": self.engine.snapshot()})
            async for raw in ws:
                request_id = None
                try:
                    request = json.loads(raw)
                    if not isinstance(request, dict):
                        raise ValueError("Expected a request object")
                    request_id = request.get("id")
                    if not isinstance(request_id, str) or len(request_id) > 80 or not isinstance(request.get("args", {}), dict):
                        raise ValueError("Invalid request shape")
                    result = await self.rpc(request.get("op"), request.get("args", {}))
                    await self.send(ws, {"type": "response", "id": request_id, "result": result})
                except ValueError as error:
                    await self.send(ws, {"type": "response", "id": request_id, "error": str(error)})
                except Exception:
                    await self.send(ws, {"type": "response", "id": request_id, "error": "Operation failed; no data was exported."})
        except (ConnectionClosed, asyncio.TimeoutError, ValueError, TypeError):
            pass
        finally:
            self.authenticating -= 1
            if authenticated:
                self.owner = None
                try:
                    await asyncio.to_thread(self.engine.stop, "Candidate dashboard disconnected")
                except Exception:
                    pass  # Engine closes camera before attempting the audit write.

    async def monitor(self):
        while not self.halt.is_set():
            try:
                snapshot = await asyncio.to_thread(self.engine.poll)
                if self.owner is not None:
                    await self.send(self.owner, {"type": "snapshot", "snapshot": snapshot})
            except (ConnectionClosed, asyncio.TimeoutError):
                if self.owner is not None:
                    await self.owner.close()
            except Exception:
                try:
                    await asyncio.to_thread(self.engine.stop, "Integrity worker error; monitoring stopped")
                except Exception:
                    pass
                if self.owner is not None:
                    await self.send(self.owner, {"type": "fatal", "error": "Monitoring stopped after a worker or audit error."})
            try:
                await asyncio.wait_for(self.halt.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    async def watchdog(self):
        # Independent of the sampling coroutine and WebSocket send backpressure.
        while not self.halt.is_set():
            try:
                await asyncio.to_thread(self.engine.watchdog)
            except Exception:
                self.halt.set()
                raise
            try:
                await asyncio.wait_for(self.halt.wait(), timeout=.5)
            except asyncio.TimeoutError:
                pass

    async def run(self, ready):
        origins = DESKTOP_ORIGINS + (DEV_ORIGINS if self.dev else [])
        async with serve(self.handle, "127.0.0.1", 0, origins=origins, max_size=65536,
                         max_queue=4, compression=None, open_timeout=5, close_timeout=2) as server:
            endpoint = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            ready({"endpoint": endpoint, "token": self.token})
            monitor = asyncio.create_task(self.monitor())
            watchdog = asyncio.create_task(self.watchdog())
            try:
                await self.halt.wait()
            finally:
                await asyncio.to_thread(self.engine.stop, "Desktop application closed")
                await asyncio.gather(monitor, watchdog)


async def main():
    # Parent delivers capability token through an anonymous stdin pipe, never argv.
    config = json.loads(sys.stdin.readline())
    if not isinstance(config.get("token"), str) or len(config["token"]) < 32:
        raise ValueError("A strong parent-issued token is required")
    service = Service(Engine(config["data_dir"]), config["token"], config.get("dev") is True)
    def ready(info):
        print(json.dumps(info), flush=True)  # Private stdout pipe consumed by Rust.
    async def parent_lifetime():
        await asyncio.to_thread(sys.stdin.read)
        service.halt.set()
    watcher = asyncio.create_task(parent_lifetime())
    try:
        await service.run(ready)
    finally:
        watcher.cancel()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    asyncio.run(main())
