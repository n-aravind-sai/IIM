"""Real-socket regressions for resource bounds on the reporting HTTP API."""
import socket
import tempfile
import threading
import time
import unittest

from cloud.server import make_server


class HttpLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sockets = []
        self.server = None
        self.writer = "w" * 32

    def start_server(self, **overrides):
        options = dict(header_timeout=0.4, body_timeout=0.4, max_connections=2)
        options.update(overrides)
        self.server = make_server(
            port=0, directory=self.tmp.name, write_token=self.writer,
            read_token="r" * 32, trusted_keys=["test-key"], **options,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.02},
            daemon=True,
        )
        self.thread.start()

    def tearDown(self):
        for connection in self.sockets:
            connection.close()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        self.tmp.cleanup()

    def connect(self):
        connection = socket.create_connection(self.server.server_address, timeout=1)
        self.sockets.append(connection)
        return connection

    def assert_drip_is_terminated(self, connection, initial, drip):
        """An idle timeout alone is defeated because a byte arrives every 25 ms."""
        connection.sendall(initial)
        connection.settimeout(0.025)
        started = time.monotonic()
        while time.monotonic() - started < 1.2:
            try:
                connection.sendall(drip)
                reply = connection.recv(4096)
                if not reply:
                    return
                # An explicit error response must still terminate the connection.
                self.assertNotIn(b" 201 ", reply)
            except socket.timeout:
                continue
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                return
        self.fail("Connection outlived its absolute deadline despite continuous drip bytes")

    def test_header_deadline_is_not_renewed_by_drip_bytes(self):
        self.start_server()
        self.assert_drip_is_terminated(
            self.connect(), b"GET /v1/reports/missing HTTP/1.1\r\nX-Drip: ", b"x",
        )

    def test_authenticated_body_deadline_is_not_renewed_by_drip_bytes(self):
        self.start_server()
        request = (
            "POST /v1/reports HTTP/1.1\r\n"
            f"Authorization: Bearer {self.writer}\r\n"
            "Content-Length: 4096\r\n\r\n"
        ).encode("ascii")
        self.assert_drip_is_terminated(self.connect(), request, b" ")

    def test_connection_limit_rejects_excess_and_releases_closed_slot(self):
        self.start_server(header_timeout=3)
        entered = threading.Condition()
        handler_count = 0
        original_handler = self.server.RequestHandlerClass

        class ObservedHandler(original_handler):
            def handle(self):
                nonlocal handler_count
                with entered:
                    handler_count += 1
                    entered.notify_all()
                return super().handle()

        self.server.RequestHandlerClass = ObservedHandler
        first = self.connect()
        first.sendall(b"GET / HTTP/1.1\r\nX-Drip: ")
        second = self.connect()
        second.sendall(b"GET / HTTP/1.1\r\nX-Drip: ")
        with entered:
            self.assertTrue(entered.wait_for(lambda: handler_count >= 2, timeout=1))

        excess = self.connect()
        excess.settimeout(0.5)
        try:
            reply = excess.recv(4096)
        except socket.timeout:
            self.fail("Excess connection remained open instead of being rejected")
        except (ConnectionResetError, ConnectionAbortedError):
            reply = b""
        self.assertTrue(not reply or b" 503 " in reply, reply)
        with entered:
            self.assertEqual(handler_count, 2, "Excess connection allocated a handler")

        first.close()
        # Slot release happens on the handler thread; retry until its cleanup runs.
        recovered = False
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            candidate = self.connect()
            candidate.settimeout(0.2)
            try:
                candidate.sendall(b"GET /v1/reports/missing HTTP/1.1\r\n\r\n")
                if b" 401 " in candidate.recv(4096):
                    recovered = True
                    break
            except (socket.timeout, ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
            finally:
                candidate.close()
            time.sleep(0.02)
        self.assertTrue(recovered, "Closing an incomplete request did not release its slot")


if __name__ == "__main__":
    unittest.main()
