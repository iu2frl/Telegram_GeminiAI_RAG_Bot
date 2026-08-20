"""Tests for the health and readiness endpoints."""

import json
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from modules import state
from modules.health import HealthServer


class HealthServerTests(unittest.TestCase):
    """Verify health probe status codes and response bodies."""

    def setUp(self):
        self.previous_ready = state.HEALTH_READY
        self.previous_reloading = state.RELOADING_GEMINI
        self.server = HealthServer(host="127.0.0.1", port=0)
        self.server.start()
        self.base_url = f"http://127.0.0.1:{self.server.address[1]}"

    def tearDown(self):
        state.HEALTH_READY = self.previous_ready
        state.RELOADING_GEMINI = self.previous_reloading
        self.server.stop()

    def request(self, path):
        try:
            with urlopen(self.base_url + path, timeout=2) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_liveness_is_available_before_ready(self):
        state.HEALTH_READY = False

        status, payload = self.request("/healthz")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_readiness_requires_initialization(self):
        state.HEALTH_READY = False

        status, payload = self.request("/readyz")

        self.assertEqual(status, 503)
        self.assertEqual(payload, {"status": "not_ready"})

    def test_readiness_is_unavailable_during_reload(self):
        state.HEALTH_READY = True
        state.RELOADING_GEMINI = True

        status, payload = self.request("/readyz")

        self.assertEqual(status, 503)
        self.assertEqual(payload, {"status": "not_ready"})

    def test_readiness_is_available_after_initialization(self):
        state.HEALTH_READY = True
        state.RELOADING_GEMINI = False

        status, payload = self.request("/readyz")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ready"})

    def test_unknown_path_returns_not_found(self):
        status, payload = self.request("/unknown")

        self.assertEqual(status, 404)
        self.assertEqual(payload, {"status": "not_found"})


if __name__ == "__main__":
    unittest.main()
