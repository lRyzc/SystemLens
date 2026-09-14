import json
import unittest
from urllib.request import urlopen

from systemlens.desktop import run


class FakeWindow:
    def __init__(self, fail=False):
        self.settings = {}
        self.fail = fail
        self.url = None
        self.payload = None

    def create_window(self, title, url, **kwargs):
        self.url = url

    def start(self, **kwargs):
        with urlopen(self.url + '/api/metrics', timeout=5) as response:
            self.payload = json.load(response)
        if self.fail:
            raise RuntimeError('Window initialization failed')


class DesktopTests(unittest.TestCase):
    def test_closing_window_stops_local_server(self):
        window = FakeWindow()
        run(window)
        self.assertIn('samples', window.payload)
        self.assertTrue(window.settings['ALLOW_DOWNLOADS'])
        with self.assertRaises(OSError):
            urlopen(window.url, timeout=1)

    def test_window_failure_stops_local_server(self):
        window = FakeWindow(fail=True)
        with self.assertRaises(RuntimeError):
            run(window)
        with self.assertRaises(OSError):
            urlopen(window.url, timeout=1)
