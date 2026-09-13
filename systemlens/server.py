"""Loopback-only HTTP interface. No remote assets, telemetry or disk persistence."""

import csv
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
from urllib.parse import urlsplit

STATIC = Path(__file__).parent / "static"
CSV_FIELDS = ("timestamp", "cpu", "memory_percent", "memory_used", "memory_total",
              "download", "upload", "disk_read", "disk_write", "temperature", "process_count")


def export_csv(samples):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(samples)
    return output.getvalue().encode("utf-8-sig")


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, collector, **kwargs):
        self.collector = collector
        super().__init__(*args, **kwargs)

    def log_message(self, *_):
        pass

    def respond(self, code, body, mime, attachment=None):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        # Reject DNS rebinding and cross-origin reads of local hardware data.
        if self.headers.get("Host") not in allowed or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.respond(403, b"Forbidden", "text/plain")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in allowed}:
            return self.respond(403, b"Forbidden", "text/plain")
        path = urlsplit(self.path).path
        if path == "/api/metrics":
            payload = self.collector.snapshot()
            return self.respond(200, json.dumps(payload, allow_nan=False).encode(), "application/json; charset=utf-8")
        if path == "/api/export":
            return self.respond(200, export_csv(self.collector.snapshot()["samples"]),
                                "text/csv; charset=utf-8", "systemlens-metrics.csv")
        files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                 "/style.css": ("style.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
        if path not in files:
            return self.respond(404, b"Not found", "text/plain")
        filename, mime = files[path]
        return self.respond(200, (STATIC / filename).read_bytes(), mime + "; charset=utf-8")


def create_server(collector, port=8765):
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, collector=collector))
