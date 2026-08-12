import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from oauth2agent.core import _expect_json_success


def test_form_encoded_request_round_trip():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            received["content_type"] = self.headers.get("Content-Type")
            received["form"] = parse_qs(self.rfile.read(length).decode("ascii"))
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/token"
        result = _expect_json_success("POST", url, form_body={"code": "a b", "grant_type": "authorization_code"})
        assert result == {"ok": True}
        assert received["content_type"] == "application/x-www-form-urlencoded"
        assert received["form"] == {"code": ["a b"], "grant_type": ["authorization_code"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
