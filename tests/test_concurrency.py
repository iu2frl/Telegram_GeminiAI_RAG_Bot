"""Concurrency tests for shared bot state and reload coordination."""

from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest

from modules import state
from modules.user_context import UserContextStore


class ConcurrencyTests(unittest.TestCase):
    """Verify concurrent operations remain isolated and serialized where required."""

    def test_concurrent_context_updates_remain_isolated(self):
        store = UserContextStore(max_turns=20, max_chars=10000)

        def add_user_context(user_id: int):
            for turn_number in range(10):
                store.add_turn(user_id, f"user-{user_id}-question-{turn_number}", "answer")

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(add_user_context, range(8)))

        for user_id in range(8):
            context = store.format_for_prompt(user_id)
            self.assertEqual(context.count(f"user-{user_id}-question-"), 10)
            for other_user_id in range(8):
                if other_user_id != user_id:
                    self.assertNotIn(f"user-{other_user_id}-question-", context)

    def test_gemini_operation_lock_serializes_reload_and_query(self):
        active_operations = 0
        maximum_active_operations = 0
        counter_lock = threading.Lock()

        def operation():
            nonlocal active_operations, maximum_active_operations
            with state.GEMINI_OPERATION_LOCK:
                with counter_lock:
                    active_operations += 1
                    maximum_active_operations = max(maximum_active_operations, active_operations)
                time.sleep(0.01)
                with counter_lock:
                    active_operations -= 1

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda _value: operation(), range(8)))

        self.assertEqual(maximum_active_operations, 1)


if __name__ == "__main__":
    unittest.main()
