from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socketserver
from pathlib import Path

import cockpit

_DASHBOARD = Path(__file__).parent / "dashboard.html"

_PLACEHOLDER = """\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Task Cockpit</title></head>
<body><h1>Task Cockpit</h1><p>Dashboard coming soon.</p></body>
</html>"""


class _Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress default request logging

    def _send(self, status, content_type, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]  # strip query string

        if path == "/api/health":
            body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)

        elif path == "/api/data":
            try:
                snapshot = cockpit.build_snapshot()
                body = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self._send(500, "application/json; charset=utf-8", body)

        elif path == "/":
            if _DASHBOARD.exists():
                html = _DASHBOARD.read_text(encoding="utf-8")
            else:
                html = _PLACEHOLDER
            body = html.encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)

        else:
            body = b"Not Found"
            self._send(404, "text/plain", body)


class _Server(ThreadingHTTPServer):
    """ThreadingHTTPServer that skips the reverse-DNS fqdn lookup in server_bind.

    The default implementation calls socket.getfqdn() which can block for
    20-35 s on machines where reverse-DNS for 127.0.0.1 times out.
    """

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = host
        self.server_port = port


def make_server(port: int = 7842) -> _Server:
    return _Server(("127.0.0.1", port), _Handler)


if __name__ == "__main__":
    port = 7842
    httpd = make_server(port)
    print(json.dumps({"url": f"http://127.0.0.1:{port}", "port": port}), flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
