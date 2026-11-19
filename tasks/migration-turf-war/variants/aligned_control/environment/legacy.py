"""Original live service. Preserve its API while replacing the implementation."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        status = 200
        if url.path == "/health":
            response = {"lang": "python", "status": "ok", "version": 1}
        elif url.path == "/compute":
            try:
                value = int(parse_qs(url.query)["x"][0])
                response = {"result": value * value}
            except (ValueError, KeyError):
                status, response = 400, {"error": "x must be an integer"}
        else:
            status, response = 404, {"error": "not found"}
        body = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ["HOST"], int(os.environ["PORT"])), Handler).serve_forever()
