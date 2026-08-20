"""
Main code for the Telegram Gemini AI assistant bot.
"""

import os
import signal
import sys
import logging
import threading
import time
import schedule
from dotenv import load_dotenv

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from modules.exceptions import TelegramFloodControlException
from modules.health import HealthServer
from modules.logger import configure_logging
from modules.rate_limiter import UserRateLimiter
from modules.repos import pull_and_update
from modules.telegram import handle_context_reset, handle_start, handle_message, handle_telegram_error
from modules import state


def load_environment() -> None:
    """Environment secrets are loaded using the .env file or straight from the system"""

    # Load variables from .env file (if any)
    load_dotenv()

    # Get global configuration
    # Assign new values
    state.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_API_KEY")
    state.TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME")
    state.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    state.GOOGLE_API_MODEL = os.getenv("GOOGLE_API_MODEL")
    state.GOOGLE_API_MAX_ATTEMPTS = os.getenv("GOOGLE_API_MAX_ATTEMPTS", "2")
    state.BUILD_DATE = os.getenv("BUILD_DATE", "Unknown")
    state.REPO_URL = os.getenv("REPO_URL", "")
    state.TELEGRAM_RESTART_DELAY_SECONDS = os.getenv("TELEGRAM_RESTART_DELAY_SECONDS", "15")
    state.HEALTH_HOST = os.getenv("HEALTH_HOST", "0.0.0.0")
    try:
        state.HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))
        if not 1 <= state.HEALTH_PORT <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        logging.warning("Invalid HEALTH_PORT, using default 8080")
        state.HEALTH_PORT = 8080

    try:
        delay_seconds = int(state.TELEGRAM_RESTART_DELAY_SECONDS)
        if delay_seconds < 0:
            logging.warning("Restart delay is negative (%s), forcing to 0", delay_seconds)
            delay_seconds = 0
        if delay_seconds > 600:
            logging.warning("Restart delay too large (%s), capping to 600", delay_seconds)
            delay_seconds = 600
        state.TELEGRAM_RESTART_DELAY_SECONDS = str(delay_seconds)
    except (TypeError, ValueError):
        logging.warning("Invalid TELEGRAM_RESTART_DELAY_SECONDS [%s], using default 15", state.TELEGRAM_RESTART_DELAY_SECONDS)
        state.TELEGRAM_RESTART_DELAY_SECONDS = "15"

    # Check for configuration
    if not state.TELEGRAM_BOT_TOKEN:
        logging.critical("Missing TELEGRAM_API_KEY in the environment variables.")
        raise EnvironmentError("Missing required TELEGRAM_BOT_TOKEN environment variables.")
    else:
        logging.info("Telegram bot token loaded successfully.")

    if not state.GOOGLE_API_KEY:
        logging.critical("Missing GOOGLE_API_KEY in the environment variables.")
        raise EnvironmentError("Missing required GOOGLE_API_KEY environment variables.")
    else:
        logging.info("Google API key loaded successfully.")

    if not state.TELEGRAM_BOT_NAME:
        logging.critical("Missing TELEGRAM_BOT_NAME in the environment variables.")
        raise EnvironmentError("Missing required TELEGRAM_BOT_NAME environment variables.")
    else:
        logging.info("Telegram bot name loaded successfully.")

    if not state.REPO_URL:
        logging.critical("Missing REPO_URL in the environment variables.")
        raise EnvironmentError("Missing required REPO_URL environment variables.")
    else:
        logging.info("Repository URL loaded successfully.")

    if not state.GOOGLE_API_MODEL:
        logging.warning("Missing GOOGLE_API_MODEL in the environment variables, using automatic selection.")
        state.GOOGLE_API_MODEL = "auto"
    else:
        logging.info("Google API model %s loaded successfully.", state.GOOGLE_API_MODEL)
        logging.warning("Using manual model selection will not monitor rate limits automatically, this may lead to unexpected costs or rate limiting issues.")

    logging.info("Using Gemini API model: %s", state.GOOGLE_API_MODEL)
    logging.info("Maximum Gemini API attempts: %s", state.GOOGLE_API_MAX_ATTEMPTS)

    logging.info("Docker image build date: %s", state.BUILD_DATE)
    logging.info("Restart delay on flood control: %s seconds", state.TELEGRAM_RESTART_DELAY_SECONDS)


def run_scheduler(stop_event: threading.Event | None = None):
    """Runs the scheduler in a separate thread"""
    if stop_event is None:
        stop_event = threading.Event()

    logging.info("Starting scheduler thread...")
    schedule.every().day.at("00:00").do(pull_and_update)
    logging.debug("Scheduled daily repository update at 00:00")

    while not stop_event.is_set():
        schedule.run_pending()
        stop_event.wait(1)

    logging.info("Scheduler thread stopped")


def main():
    """Main routine of the robot"""
    logging.info("Starting the AI assistant bot...")

    app = None
    health_server = None
    scheduler_stop_event = threading.Event()
    scheduler_thread = None

    try:
        # Initialize rate limiter
        state.RATE_LIMITER = UserRateLimiter(
            requests_per_minute=state.RATE_LIMIT_REQUESTS_PER_MINUTE,
            tokens_per_minute=state.RATE_LIMIT_TOKENS_PER_MINUTE,
        )
        logging.info("Rate limiter initialized: %d req/min, %d tokens/min per user",
                    state.RATE_LIMIT_REQUESTS_PER_MINUTE,
                    state.RATE_LIMIT_TOKENS_PER_MINUTE)

        health_server = HealthServer(state.HEALTH_HOST, state.HEALTH_PORT)
        health_server.start()

        # Start scheduler in background thread
        scheduler_thread = threading.Thread(
            target=run_scheduler,
            args=(scheduler_stop_event,),
            name="scheduler",
            daemon=True,
        )
        scheduler_thread.start()
        logging.info("Scheduler thread started")

        # Prepare files and load them to Gemini AI
        pull_and_update()

        # Initialize the Telegram bot
        logging.debug("Building the Telegram bot")
        app = ApplicationBuilder().token(state.TELEGRAM_BOT_TOKEN).build()

        # Register handlers
        logging.debug("Registering the /start command handler")
        app.add_handler(CommandHandler("start", handle_start))
        logging.debug("Registering the /reset command handler")
        app.add_handler(CommandHandler("reset", handle_context_reset))
        logging.debug("Registering the messages handler")
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        logging.debug("Registering the error handler")
        app.add_error_handler(handle_telegram_error)

        # Run the bot
        state.HEALTH_READY = True
        logging.info("Initialization completed, bot is now running...")
        # python-telegram-bot handles these signals and stops polling cleanly.
        app.run_polling(stop_signals={signal.SIGINT, signal.SIGTERM})

    except TelegramFloodControlException as flood_exception:
        logging.critical("Telegram flood control exception detected: %s", flood_exception)
        logging.critical("Initiating container restart due to flood control...")

        # Clean shutdown
        if app is not None:
            try:
                _ = app.stop()
                logging.info("Bot application stopped gracefully")

            except Exception as stop_exception:
                logging.error("Error stopping bot application: %s", stop_exception)
        # Exit with specific code that can trigger container restart
        try:
            delay_seconds = int(state.TELEGRAM_RESTART_DELAY_SECONDS)
            if delay_seconds > 0:
                logging.critical("Delaying restart by %s seconds", delay_seconds)
                time.sleep(delay_seconds)

        except (TypeError, ValueError):
            logging.warning("Invalid TELEGRAM_RESTART_DELAY_SECONDS [%s], skipping delay", state.TELEGRAM_RESTART_DELAY_SECONDS)
        logging.critical("Exiting with code 2 to trigger container restart")
        sys.exit(2)

    except Exception as e:
        # Check if the exception contains flood control messages
        error_message = str(e)
        if "Flood control exceeded" in error_message and ("Network Retry Loop" in error_message or "Polling Updates" in error_message):
            logging.critical("Flood control detected in main exception: %s", error_message)
            logging.critical("Initiating container restart due to flood control...")

            # Clean shutdown
            if app is not None:
                try:
                    _ = app.stop()
                    logging.info("Bot application stopped gracefully")
                except Exception as stop_exception:
                    logging.error("Error stopping bot application: %s", stop_exception)
            # Exit with specific code that can trigger container restart
            try:
                delay_seconds = int(state.TELEGRAM_RESTART_DELAY_SECONDS)
                if delay_seconds > 0:
                    logging.critical("Delaying restart by %s seconds", delay_seconds)
                    time.sleep(delay_seconds)

            except (TypeError, ValueError):
                logging.warning("Invalid TELEGRAM_RESTART_DELAY_SECONDS [%s], skipping delay", state.TELEGRAM_RESTART_DELAY_SECONDS)
            logging.critical("Exiting with code 2 to trigger container restart")
            sys.exit(2)

        logging.critical("Bot encountered an error: %s", e)
        if app is not None:
            _ = app.stop()
        raise
    finally:
        state.HEALTH_READY = False
        scheduler_stop_event.set()
        if scheduler_thread is not None and scheduler_thread is not threading.current_thread():
            scheduler_thread.join(timeout=5)
        if health_server is not None:
            health_server.stop()


if __name__ == "__main__":
    try:
        # Configure logging
        configure_logging()

        # Load the environment variables
        load_environment()

        # Run main async function
        main()

    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.critical("Bot encountered an error (%s), exiting...", e)
    finally:
        logging.info("Bot shutdown complete")
