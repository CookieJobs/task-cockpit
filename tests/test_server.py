import os, json, tempfile, unittest, threading, urllib.request, importlib
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
