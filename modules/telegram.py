
import asyncio
import logging

from telegram import Update
from telegram.error import BadRequest, Conflict, NetworkError, RetryAfter
from telegram.ext import ContextTypes

from modules import state
from modules.exceptions import GeminiQueryException, TelegramFloodControlException
from modules.gemini import gemini_initialize, gemini_query_sources
from modules.helpers import (
    ZERO_WIDTH_SPACE,
    _format_markdown_v2,
    _split_telegram_message,
    remove_markdown,
    render_latex_to_png_bytes,
    split_text_with_latex,
)


async def handle_start(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    logging.info("Received /start command from user: [%s], id: [%s]", update.effective_sender.name, update.effective_user.id)
    await update.message.reply_text("Hello! Send me a message with your question, and I'll do my best to help you!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes user messages and replies with the PDF query result."""
    user_message_content = str(update.message.text)
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    logging.debug("Received message from user [%s] from chat_id: [%s]", user_id, chat_id)

    if chat_id <= 0:
        # Message is coming from a group
        user_message_content = user_message_content.lstrip()
        bot_name = state.TELEGRAM_BOT_NAME or ""
        if bot_name.startswith("@"): 
            bot_name = bot_name[1:]
        mention_variants = {bot_name, f"@{bot_name}"} if bot_name else set()

        if not any(user_message_content.lower().startswith(name.lower()) for name in mention_variants):
            # Ignore messages from groups if not directed to the bot
            logging.debug("Ignoring message from group [%s] by user [%s] as it was not directed to the bot", chat_id, user_id)
            return
        else:
            # Remove the bot name from the query
            for name in sorted(mention_variants, key=len, reverse=True):
                if user_message_content.lower().startswith(name.lower()):
                    user_message_content = user_message_content[len(name) :]
                    break
            user_message_content = user_message_content.lstrip(" :,-")

    user_message_content = user_message_content.strip()

    if not user_message_content:
        logging.debug("Ignoring empty message from user [%s] from chat_id [%s]", user_id, chat_id)
        return

    if len(user_message_content) < 3:
        logging.debug("Ignoring too short message from user [%s] from chat_id [%s]", user_id, chat_id)
        return

    if len(user_message_content) > 500:
        logging.warning("Ignoring too long message from user [%s] from chat_id [%s]", user_id, chat_id)
        await update.message.reply_text("Your message is too long, please shorten it and try again.")
        return

    if len(user_message_content) > 400:
        logging.warning("Warning: Message from user [%s] from chat_id [%s] is lengthy", user_id, chat_id)
        await update.message.reply_text("Your message is lengthy, please consider shortening it for better responses.")

    logging.info("Processing valid message from user [%s] from chat_id [%s], content: %s", user_id, chat_id, user_message_content)

    # Send the cleaned request to the AI
    await bot_reply_to_message(update, context, user_message_content.strip())


async def bot_reply_to_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message_content: str):
    """
    This routine handles the cleaned request from the user and passes it to the Gemini APIs.
    Result is then sent to the user
    """
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    # Send a placeholder message and get the message ID
    processing_message = await update.message.reply_text("<i>Processing your request...</i>", parse_mode="html")
    logging.debug("Sent placeholder message, waiting for AI to reply.")

    if state.RELOADING_GEMINI:
        # If the Gemini API is being reloaded, wait for it to complete
        logging.info("Gemini API is being reloaded, waiting for it to complete.")
        await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, "The source files on the server are being updated, please wait...")
        while state.RELOADING_GEMINI:
            await asyncio.sleep(1)

    # Query the Gemini API with a limited number of attempts (defined in the environment)
    logging.debug("User [%s] with ID [%i] asked: [%s]", update.effective_user.name, user_id, user_message_content)

    try:
        max_attempts = int(state.GOOGLE_API_MAX_ATTEMPTS)
        if max_attempts < 1:
            max_attempts = 2
    except (TypeError, ValueError):
        logging.warning("Invalid GOOGLE_API_MAX_ATTEMPTS [%s], using default 2", state.GOOGLE_API_MAX_ATTEMPTS)
        max_attempts = 2
    last_error = ""
    telegram_error_message = "Please wait..."

    for i in range(max_attempts):
        try:
            logging.debug("Trying to request answer from Gemini AI, tentative %i out of %s", i + 1, max_attempts)
            # Request data from Gemini AI by offloading gemini_query_sources to a thread
            result = await gemini_query_sources(user_message_content)
            logging.debug("Got a result from Gemini, passing it to the Telegram APIs")
            # Replace the placeholder message with the actual result
            await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, result)
            logging.debug("Answer from AI: [%s]", result)
            logging.info("Replied to user [%s] from chat_id: [%s]", user_id, chat_id)
            # Exit the loop if successful
            return
        except GeminiQueryException as gemini_error:
            error_message = str(gemini_error)
            last_error = f"Error retrieving answer from AI: {error_message}"
            logging.error("Last error: %s", last_error)
            error_code = 0
            try:
                last_error = f"Error retrieving answer from AI: {error_message}"
                logging.warning(last_error)
                # Extract the error code from the message
                error_code = int(str(error_message).split(" ", maxsplit=1)[0])
                logging.warning("Gemini APIs returned error code: [%i]", error_code)
                # Handle the error code
                if 500 <= error_code < 600:
                    # If service timeout, try again later
                    telegram_error_message = "The bot is thinking hard, but he will be back soon, please wait..."
                elif 400 <= error_code < 500:
                    # For some reason we cannot connect load the files (permission error) - Files are probably expired
                    telegram_error_message = "The source files are being updated, please wait..."
                    if error_code == 403:
                        # If permission denied, files are expired, reload them
                        logging.warning("Files might be expired, need to reload them")
                        try:
                            state.RELOADING_GEMINI = True
                            gemini_initialize()
                        except Exception as gemini_init_exception:
                            logging.critical("Failed to reload files, error: %s", gemini_init_exception)
                            last_error = f"Error reloading files: {str(gemini_init_exception)}"
                        finally:
                            state.RELOADING_GEMINI = False
                else:
                    # Something bad happeneded and needs to be fixed
                    telegram_error_message = "Unexpected server error, please trying again later."
                    logging.critical("Exiting the for loop due to an unhandled error: %s", error_message)
                    break
            except ValueError:
                # Cannot get the server error from Gemini
                last_error = f"Error converting error code from AI: {error_message}"
                logging.warning(last_error)
                telegram_error_message = "Unexpected server error, trying again, please be patient"
        except Exception as generic_exception:
            telegram_error_message = "Unexpected server error, trying again, please be patient"
            last_error = f"Unexpected error occurred while querying Gemini API: {str(generic_exception)}"
            logging.error(last_error)

        logging.warning("Waiting 3 seconds before next attempt, sending answer to client")
        await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, telegram_error_message)
        await asyncio.sleep(3)

    logging.error("Error while creating an answer for user [%s]: %s", user_id, last_error)
    # Replace the placeholder message with an error message
    await bot_send_message(context, processing_message.chat_id, "Sorry, something went wrong while processing your request, please try again later.")
    logging.debug("Updated message with error notification.")


async def bot_edit_text(context, chat_id, message_id, text: str):
    """
    Edits the message with the content of the file.
    """
    try:
        logging.debug("Sending edited message")
        segments = split_text_with_latex(text)
        has_latex = any(segment_type == "latex" for segment_type, _ in segments)

        if not has_latex:
            escaped_text = _format_markdown_v2(text).strip()
            chunks = _split_telegram_message(escaped_text)
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=chunks[0],
                parse_mode="MarkdownV2",
            )
            for chunk in chunks[1:]:
                await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")
            return

        first_sent = False
        for segment_type, segment_content in segments:
            if segment_type == "text":
                if not segment_content.strip():
                    continue
                escaped_text = _format_markdown_v2(segment_content).strip()
                if not escaped_text:
                    continue
                chunks = _split_telegram_message(escaped_text)
                if not first_sent:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=chunks[0],
                        parse_mode="MarkdownV2",
                    )
                    for chunk in chunks[1:]:
                        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")
                    first_sent = True
                else:
                    for chunk in chunks:
                        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")
                continue

            latex_bytes = render_latex_to_png_bytes(segment_content)
            if not first_sent:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=ZERO_WIDTH_SPACE,
                    parse_mode="MarkdownV2",
                )
                first_sent = True

            if latex_bytes:
                await context.bot.send_photo(chat_id=chat_id, photo=latex_bytes)
            else:
                fallback_text = _format_markdown_v2(f"${segment_content}$").strip()
                for chunk in _split_telegram_message(fallback_text):
                    await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")
    except RetryAfter as retry_exception:
        # Handle flood control specifically
        retry_seconds = retry_exception.retry_after
        logging.warning("Telegram flood control triggered. Retry after %s seconds", retry_seconds)
        
        # Check if this is the specific flood control error from the Network Retry Loop
        error_message = str(retry_exception)
        if "Flood control exceeded" in error_message and "Network Retry Loop" in error_message:
            logging.critical("Network Retry Loop flood control detected: %s", error_message)
            raise TelegramFloodControlException(
                f"Flood control exceeded in Network Retry Loop: {error_message}"
            ) from retry_exception
        
        # For regular flood control, wait and retry
        await asyncio.sleep(retry_seconds + 1)  # Add 1 second buffer
        try:
            chunks = _split_telegram_message(escaped_text)
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=chunks[0], parse_mode="MarkdownV2")
            for chunk in chunks[1:]:
                await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="MarkdownV2")
        except Exception as retry_edit_exception:
            logging.error("Failed to edit message after flood control retry: %s", retry_edit_exception)
            raise
    except BadRequest as bad_request_exception:
        if "Message is not modified" in str(bad_request_exception):
            logging.debug("Skipping edit: message is not modified")
            return
        logging.error("Bad request while editing message: %s", bad_request_exception)
        raise
    except NetworkError as network_exception:
        # Check for flood control in network errors
        error_message = str(network_exception)
        if "Flood control exceeded" in error_message:
            logging.critical("Network-level flood control detected: %s", error_message)
            raise TelegramFloodControlException(
                f"Network flood control exceeded: {error_message}"
            ) from network_exception
        logging.error("Network error while editing message: %s", network_exception)
        raise
    except Exception as ret_exception:
        # Check for flood control in generic exceptions
        error_message = str(ret_exception)
        if "Flood control exceeded" in error_message and ("Network Retry Loop" in error_message or "Polling Updates" in error_message):
            logging.critical("Flood control detected in polling/network retry loop: %s", error_message)
            raise TelegramFloodControlException(
                f"Flood control in polling loop: {error_message}"
            ) from ret_exception
            
        logging.error("Failed to edit message: %s", ret_exception)
        try:
            # Fallback to plain text if MarkdownV2 fails
            logging.debug("Trying to edit message with plain text")
            text = remove_markdown(text).strip()
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
        except Exception as edit_exception:
            logging.error("Failed to edit message with fallback: %s", edit_exception)
            try:
                await context.bot.send_message(chat_id, "An error occurred, please try again later")
            except Exception as send_exception:
                logging.error("Failed to send error message: %s", send_exception)


async def bot_send_message(context, chat_id, message):
    """Send a message to the user"""
    try:
        await context.bot.send_message(chat_id, message)
    except RetryAfter as retry_exception:
        # Handle flood control specifically
        retry_seconds = retry_exception.retry_after
        logging.warning("Telegram flood control triggered in send_message. Retry after %s seconds", retry_seconds)
        
        # Check if this is the specific flood control error from the Network Retry Loop
        error_message = str(retry_exception)
        if "Flood control exceeded" in error_message and "Network Retry Loop" in error_message:
            logging.critical("Network Retry Loop flood control detected in send_message: %s", error_message)
            raise TelegramFloodControlException(
                f"Flood control exceeded in Network Retry Loop: {error_message}"
            ) from retry_exception
        
        # For regular flood control, wait and retry
        await asyncio.sleep(retry_seconds + 1)  # Add 1 second buffer
        try:
            await context.bot.send_message(chat_id, message)
        except Exception as retry_send_exception:
            logging.error("Failed to send message after flood control retry: %s", retry_send_exception)
            raise
    except NetworkError as network_exception:
        # Check for flood control in network errors
        error_message = str(network_exception)
        if "Flood control exceeded" in error_message:
            logging.critical("Network-level flood control detected in send_message: %s", error_message)
            raise TelegramFloodControlException(
                f"Network flood control exceeded: {error_message}"
            ) from network_exception
        logging.error("Network error while sending message: %s", network_exception)
        raise
    except Exception as send_exception:
        # Check for flood control in generic exceptions
        error_message = str(send_exception)
        if "Flood control exceeded" in error_message and ("Network Retry Loop" in error_message or "Polling Updates" in error_message):
            logging.critical("Flood control detected in send_message polling/network retry loop: %s", error_message)
            raise TelegramFloodControlException(
                f"Flood control in polling loop: {error_message}"
            ) from send_exception
        logging.error("Error sending message: %s", send_exception)
        raise


async def handle_telegram_error(_update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Centralized error handler for Telegram polling issues."""
    error = context.error
    if isinstance(error, Conflict):
        logging.critical("Telegram Conflict: %s", error)
        raise TelegramFloodControlException("Another bot instance is running. Restart to recover.")
    if isinstance(error, NetworkError):
        logging.error("Telegram NetworkError: %s", error)
        return
    logging.exception("Unhandled Telegram error: %s", error)
