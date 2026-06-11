import os, json, tempfile, unittest, threading, urllib.request, importlib, urllib.error
from pathlib import Path

class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["TASK_COCKPIT_DIR"] = self.tmp
        import cockpit; importlib.reload(cockpit); self.c = cockpit
        import server; importlib.reload(server); self.server_mod = server
        self.httpd = server.make_server(0)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, r.read().decode()

    def test_health(self):
        status, body = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_api_data_returns_snapshot(self):
        pid = self.c.add_project("P"); self.c.add_task(pid, "T"); self.c.confirm_drafts()
        status, body = self._get("/api/data")
        self.assertEqual(json.loads(body)["projects"][0]["name"], "P")

    def test_root_serves_dashboard_html(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("<html", body.lower())

    def test_unknown_path_returns_404(self):
        try:
            self._get("/does/not/exist")
            self.fail("Expected HTTPError for 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_api_data_returns_500_on_error(self):
        original = self.c.build_snapshot
        def _boom():
            raise RuntimeError("boom")
        self.c.build_snapshot = _boom
        try:
            try:
                self._get("/api/data")
                self.fail("Expected HTTPError for 500")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 500)
                body = json.loads(e.read().decode())
                self.assertIn("error", body)
        finally:
            self.c.build_snapshot = original
