"""HTTP health and readiness endpoints for container orchestration."""

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

from modules import state


class HealthRequestHandler(BaseHTTPRequestHandler):
    """Serves non-sensitive liveness and readiness responses."""

    def do_GET(self):
        """Handle health probe requests."""
        path = urlsplit(self.path).path

        if path in ("/health", "/healthz"):
            self._send_json(200, {"status": "ok"})
            return

        if path in ("/ready", "/readyz"):
            if state.HEALTH_READY and not state.RELOADING_GEMINI:
                self._send_json(200, {"status": "ready"})
            else:
                self._send_json(503, {"status": "not_ready"})
            return

        self._send_json(404, {"status": "not_found"})

    def _send_json(self, status_code: int, payload: dict[str, str]):
        """Send a compact JSON response without exposing configuration."""
        response_body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format_string: str, *args):
        """Send probe access logs through the application logger."""
        logging.debug("Health probe: %s", format_string % args)


class HealthServer:
    """Runs the health server in a daemon thread."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.server = ThreadingHTTPServer((host, port), HealthRequestHandler)
        self.thread = Thread(target=self.server.serve_forever, name="health-server", daemon=True)

    @property
    def address(self) -> tuple[str, int]:
        """Return the bound server address, including an ephemeral port in tests."""
        return self.server.server_address

    def start(self):
        """Start serving health probes."""
        self.thread.start()
        logging.info("Health server started on %s:%s", self.address[0], self.address[1])

    def stop(self):
        """Stop serving health probes."""
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)