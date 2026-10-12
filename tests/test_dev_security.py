import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.dev import make_dev_server


class DevelopmentSecurityTests(unittest.TestCase):
    def setUp(self):
        self.secret = 'launch-secret-' + 'x' * 32
        self.connection = {'endpoint': 'ws://127.0.0.1:12345', 'token': 'private-worker-token'}
        self.server = make_dev_server(self.connection, self.secret, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path='/bootstrap.json', **headers):
        try:
            response = urlopen(Request(self.base + path, headers=headers), timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_another_local_user_cannot_fetch_the_worker_token(self):
        status, _, body = self.request()
        self.assertEqual(status, 403)
        self.assertNotIn(self.connection['token'].encode(), body)

    def test_wrong_secret_and_worker_token_are_not_bootstrap_credentials(self):
        for token in ('wrong', self.connection['token']):
            with self.subTest(token=token):
                self.assertEqual(self.request(Authorization='Bearer ' + token)[0], 403)

    def test_valid_launch_secret_returns_connection_without_caching(self):
        status, headers, body = self.request(Authorization='Bearer ' + self.secret)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.connection)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_launch_secret_is_not_in_public_dashboard(self):
        status, _, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertNotIn(self.secret.encode(), body)
        self.assertNotIn(self.connection['token'].encode(), body)

    def test_all_dashboard_responses_forbid_framing(self):
        for path in ('/', '/app.js', '/missing-page', '/bootstrap.json'):
            with self.subTest(path=path):
                _, headers, _ = self.request(path)
                self.assertEqual(headers.get('Content-Security-Policy'), "frame-ancestors 'none'")
                self.assertEqual(headers.get('X-Frame-Options'), 'DENY')
