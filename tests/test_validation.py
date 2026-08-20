"""Tests for centralized user input validation."""

import unittest

from modules.validation import validate_user_message


class ValidationTests(unittest.TestCase):
    """Verify normalization, limits, and validation metadata."""

    def test_valid_message_is_normalized(self):
        result = validate_user_message("  Caffe\u0301  ")

        self.assertTrue(result.valid)
        self.assertEqual(result.value, "Caffé")

    def test_empty_message_is_rejected(self):
        result = validate_user_message(" \n\t ")

        self.assertFalse(result.valid)
        self.assertEqual(result.error, "empty")

    def test_short_message_is_rejected(self):
        result = validate_user_message("ab")

        self.assertFalse(result.valid)
        self.assertEqual(result.error, "too_short")

    def test_long_message_is_rejected(self):
        result = validate_user_message("x" * 501)

        self.assertFalse(result.valid)
        self.assertEqual(result.error, "too_long")

    def test_length_warning_is_reported(self):
        result = validate_user_message("x" * 401)

        self.assertTrue(result.valid)
        self.assertTrue(result.is_length_warning)

    def test_control_characters_are_removed(self):
        result = validate_user_message("hello\x00 world")

        self.assertTrue(result.valid)
        self.assertEqual(result.value, "hello world")


if __name__ == "__main__":
    unittest.main()