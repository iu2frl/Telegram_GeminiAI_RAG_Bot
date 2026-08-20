"""Tests for cooperative application shutdown."""

import threading
import unittest

from main import run_scheduler


class ShutdownTests(unittest.TestCase):
    """Verify background workers stop when requested."""

    def test_scheduler_stops_when_event_is_set(self):
        stop_event = threading.Event()
        scheduler_thread = threading.Thread(
            target=run_scheduler,
            args=(stop_event,),
            daemon=True,
        )
        scheduler_thread.start()

        stop_event.set()
        scheduler_thread.join(timeout=3)

        self.assertFalse(scheduler_thread.is_alive())


if __name__ == "__main__":
    unittest.main()