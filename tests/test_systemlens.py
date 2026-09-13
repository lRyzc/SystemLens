import csv
import http.client
import io
import json
import threading
import unittest
from unittest.mock import patch

from systemlens.collector import Collector, optional, rate
from systemlens.server import create_server, export_csv


class CollectorTests(unittest.TestCase):
    def test_rates_handle_first_read_reset_and_zero_interval(self):
        self.assertEqual(rate(1000, None, 1), 0)
        self.assertEqual(rate(1000, 500, 2), 250)
        self.assertEqual(rate(10, 500, 2), 0)
        self.assertEqual(rate(1000, 500, 0), 0)

    def test_unavailable_sensors_are_optional(self):
        with patch("systemlens.collector.psutil.sensors_battery", side_effect=NotImplementedError):
            import psutil
            self.assertIsNone(optional(psutil.sensors_battery))

    def test_live_sample_and_history(self):
        collector = Collector(interval=.05, capacity=2)
        collector.start()
        try:
            for _ in range(100):
                if collector.snapshot()["samples"] and collector.snapshot()["samples"][-1]["id"] >= 3:
                    break
                collector.stop_event.wait(.05)
            payload = collector.snapshot()
            self.assertIsNone(payload["error"])
            self.assertEqual(len(payload["samples"]), 2)
            sample = payload["samples"][-1]
            self.assertGreaterEqual(sample["id"], 3)
            self.assertGreater(sample["memory_total"], 0)
            self.assertTrue(0 <= sample["cpu"] <= 100)
            self.assertTrue(0 <= sample["memory_percent"] <= 100)
            self.assertGreater(len(payload["latest"]["cores"]), 0)
            self.assertNotIn("processes", sample)
            json.dumps(payload, allow_nan=False)
        finally:
            collector.stop()
        self.assertFalse(collector.thread.is_alive())

    def test_csv_preserves_units_and_does_not_export_processes(self):
        raw = export_csv([{"timestamp": "2026-01-01T00:00:00+00:00", "cpu": 12.5,
                           "download": 1024, "processes": [{"name": "private"}]}])
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(rows[0]["cpu"], "12.5")
        self.assertEqual(rows[0]["download"], "1024")
        self.assertNotIn("private", raw.decode("utf-8-sig"))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = Collector()
        cls.server = create_server(cls.collector, port=0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_empty_startup_is_valid_json(self):
        code, _, body = self.request("/api/metrics")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["samples"], [])
        self.assertIsNone(json.loads(body)["latest"])

    def test_static_assets_and_content_security(self):
        for path in ("/", "/style.css", "/app.js", "/favicon.svg"):
            with self.subTest(path=path):
                code, headers, body = self.request(path)
                self.assertEqual(code, 200)
                self.assertTrue(body)
                self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
                self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_unknown_paths_and_traversal_are_not_served(self):
        for path in ("/missing", "/../pyproject.toml", "/%2e%2e/pyproject.toml"):
            self.assertEqual(self.request(path)[0], 404)

    def test_foreign_host_and_origin_are_rejected(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"},
                        {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("/api/metrics", headers)[0], 403)

    def test_csv_download(self):
        code, headers, body = self.request("/api/export")
        self.assertEqual(code, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertTrue(body.decode("utf-8-sig").startswith("timestamp,cpu,"))


if __name__ == "__main__":
    unittest.main()
