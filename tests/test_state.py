import unittest
from datetime import datetime, timedelta, timezone

from modules import state
from modules.exceptions import GeminiApiInitializeException, GeminiQueryException


class StateTests(unittest.TestCase):
    def test_gemini_client_is_created_lazily(self):
        self.assertIsNone(state.GEMINI_CLIENT)

    def test_model_request_history_is_per_instance(self):
        first = state.GenAiModel("first", max_rpm=2, max_tpm=10, max_rpd=10)
        second = state.GenAiModel("second", max_rpm=2, max_tpm=10, max_rpd=10)

        first.add_request()

        self.assertIsNot(first.requests, second.requests)
        self.assertEqual(first.get_rpm(), 1)
        self.assertEqual(second.get_rpm(), 0)

    def test_model_rate_limits_use_current_time(self):
        model = state.GenAiModel("test", max_rpm=2, max_tpm=10, max_rpd=10)
        model.add_request(timestamp=datetime.now(timezone.utc) - timedelta(minutes=2), token_count=3)

        self.assertEqual(model.get_rpm(), 0)
        self.assertEqual(model.get_tpm(), 3)
        self.assertTrue(model.is_available())

    def test_gemini_errors_are_normal_exceptions(self):
        self.assertTrue(issubclass(GeminiApiInitializeException, Exception))
        self.assertTrue(issubclass(GeminiQueryException, Exception))


if __name__ == "__main__":
    unittest.main()