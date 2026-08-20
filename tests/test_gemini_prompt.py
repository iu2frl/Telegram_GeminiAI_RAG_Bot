import unittest
from unittest.mock import AsyncMock, patch

from modules import state
from modules.gemini import gemini_query_sources


class GeminiPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_forbids_formula_output(self):
        with patch.object(state, "TELEGRAM_BOT_NAME", "test-bot"), patch.object(
            state, "GOOGLE_API_MODEL", "test-model"
        ), patch(
            "modules.gemini.gemini_generate_content_fixed_model",
            new=AsyncMock(return_value="plain-language summary"),
        ) as generate_content:
            result = await gemini_query_sources("Explain the formula E = mc^2")

        call = generate_content.await_args
        if call is None:
            self.fail("Gemini generation was not called")
        prompt = call.args[0]
        self.assertEqual(result, "plain-language summary")
        self.assertIn("summarize their meaning in plain language only", prompt)
        self.assertIn("Never return LaTeX, TeX, math delimiters, or the original formulas", prompt)


if __name__ == "__main__":
    unittest.main()
