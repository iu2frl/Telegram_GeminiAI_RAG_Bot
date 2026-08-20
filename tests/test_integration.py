"""Integration tests for the Telegram message flow."""

import unittest
from tempfile import NamedTemporaryFile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from modules import state
from modules.rate_limiter import UserRateLimiter
from modules.telegram import handle_context_reset, handle_message
from modules.user_context import UserContextStore


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercise message handling with mocked external services."""

    async def asyncSetUp(self):
        self.previous_rate_limiter = state.RATE_LIMITER
        self.previous_context = state.USER_CONTEXT
        self.previous_attempts = state.GOOGLE_API_MAX_ATTEMPTS
        self.previous_bot_name = state.TELEGRAM_BOT_NAME
        self.rate_limit_db = NamedTemporaryFile(delete=False, suffix=".db")
        self.rate_limit_db.close()
        state.RATE_LIMITER = UserRateLimiter(
            db_path=self.rate_limit_db.name,
            requests_per_minute=10,
            tokens_per_minute=1000,
        )
        state.USER_CONTEXT = UserContextStore()
        state.GOOGLE_API_MAX_ATTEMPTS = "1"
        state.TELEGRAM_BOT_NAME = "@testbot"

    async def asyncTearDown(self):
        state.RATE_LIMITER = self.previous_rate_limiter
        state.USER_CONTEXT = self.previous_context
        state.GOOGLE_API_MAX_ATTEMPTS = self.previous_attempts
        state.TELEGRAM_BOT_NAME = self.previous_bot_name

    @staticmethod
    def make_update(user_id: int, text: str):
        processing_message = SimpleNamespace(chat_id=user_id, message_id=99)
        message = SimpleNamespace(
            text=text,
            chat_id=user_id,
            reply_text=AsyncMock(return_value=processing_message),
        )
        user = SimpleNamespace(id=user_id, name=f"user-{user_id}", full_name=f"User {user_id}")
        return SimpleNamespace(effective_user=user, message=message)

    async def test_message_flow_records_response_and_context(self):
        update = self.make_update(101, "What is the project about?")
        context = SimpleNamespace()

        with patch(
            "modules.telegram.gemini_query_sources",
            new=AsyncMock(return_value={"response": "It is a radio project.", "tokens": 12}),
        ) as query, patch(
            "modules.telegram.bot_edit_text",
            new=AsyncMock(),
        ) as edit:
            await handle_message(update, context)

        query.assert_awaited_once_with("What is the project about?", 101)
        edit.assert_awaited_once()
        self.assertEqual(
            state.USER_CONTEXT.format_for_prompt(101).count("What is the project about?"),
            1,
        )
        self.assertEqual(state.RATE_LIMITER.get_user_stats(101)["requests_used"], 1)

    async def test_users_do_not_share_context_in_message_flow(self):
        first_update = self.make_update(101, "First user's topic")
        second_update = self.make_update(202, "Second user's topic")
        context = SimpleNamespace()

        with patch(
            "modules.telegram.gemini_query_sources",
            new=AsyncMock(side_effect=[
                {"response": "First answer", "tokens": 5},
                {"response": "Second answer", "tokens": 5},
            ]),
        ) as query, patch("modules.telegram.bot_edit_text", new=AsyncMock()):
            await handle_message(first_update, context)
            await handle_message(second_update, context)

        calls = query.await_args_list
        self.assertEqual(calls[0].args, ("First user's topic", 101))
        self.assertEqual(calls[1].args, ("Second user's topic", 202))
        self.assertNotIn("Second user's topic", state.USER_CONTEXT.format_for_prompt(101))
        self.assertNotIn("First user's topic", state.USER_CONTEXT.format_for_prompt(202))

    async def test_reset_command_clears_only_requesting_user(self):
        state.USER_CONTEXT.add_turn(101, "private topic", "private answer")
        state.USER_CONTEXT.add_turn(202, "other topic", "other answer")
        update = self.make_update(101, "/reset")

        await handle_context_reset(update, SimpleNamespace())

        self.assertEqual(state.USER_CONTEXT.format_for_prompt(101), "(No previous conversation.)")
        self.assertIn("other topic", state.USER_CONTEXT.format_for_prompt(202))
        update.message.reply_text.assert_awaited_once()

    async def test_long_message_is_rejected_before_gemini(self):
        update = self.make_update(101, "x" * 501)

        with patch("modules.telegram.gemini_query_sources", new=AsyncMock()) as query:
            await handle_message(update, SimpleNamespace())

        query.assert_not_awaited()
        update.message.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
