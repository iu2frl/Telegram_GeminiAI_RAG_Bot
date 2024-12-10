import os
import logging
import re
import time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# Global variables
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_BOT_NAME = ""
GOOGLE_API_KEY = ""
GOOGLE_API_MODEL = ""
GOOGLE_API_MAX_ATTEMPTS = ""
model = None
uploaded_files = []

def configure_logging() -> None:
    """Configure logging options"""
    logging.basicConfig(
        level=logging.INFO,  # Set to DEBUG for detailed logs; use INFO in production
        format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Set specific modules to WARNING level
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

def load_environment() -> None:
    """ Environment secrets are loaded using the .env file or straight from the system"""

    # Load variables from .env file (if any)
    load_dotenv()

    # Get global configuration
    global TELEGRAM_BOT_TOKEN
    global TELEGRAM_BOT_NAME
    global GOOGLE_API_KEY
    global GOOGLE_API_MODEL
    global GOOGLE_API_MAX_ATTEMPTS

    # Assign new values
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_API_KEY")
    TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_API_MODEL = os.getenv("GOOGLE_API_MODEL", "gemini-1.5-flash")
    GOOGLE_API_MAX_ATTEMPTS = os.getenv("GOOGLE_API_MAX_ATTEMPTS", "2")

    # Check for configuration
    if not TELEGRAM_BOT_TOKEN:
        logging.critical("Missing TELEGRAM_API_KEY in the environment variables.")
        raise EnvironmentError("Missing required environment variables.")
    if not GOOGLE_API_KEY:
        logging.critical("Missing GOOGLE_API_KEY in the environment variables.")
        raise EnvironmentError("Missing required environment variables.")
    if not TELEGRAM_BOT_NAME:
        logging.critical("Missing TELEGRAM_BOT_NAME in the environment variables.")
        raise EnvironmentError("Missing required environment variables.")

def list_files_in_folder(folder_path):
    """
    Returns a list of all files in the given folder.

    Args:
        folder_path (str): Path to the folder.

    Returns:
        list: List of file names in the folder.
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"The provided path [{folder_path}] is not a directory.")

    return [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and "README.md" not in f]

def initialize_gemini() -> None:
    """Initializes the Gemini AI parameters"""

    # Global variables
    global uploaded_files
    global model

    # Configure Gemini API
    logging.info("Configuring Gemini API from environment")
    genai.configure(api_key=GOOGLE_API_KEY)

    # Initialize the Gemini model
    logging.info("Initializing Gemini model [%s] from environment", GOOGLE_API_MODEL)

    model = genai.GenerativeModel(GOOGLE_API_MODEL)

    # List of file paths to upload as source
    try:
        logging.debug("Fetching all files in the sources folder")
        file_paths = list_files_in_folder("./sources")  # Add your file paths here
        logging.info("Found %i files in sources folder", len(file_paths))
    except Exception as e:
        logging.critical("Cannot retrieve documents from sources folder, error: %s", e)
        raise

    # Upload each file and store the uploaded file references
    for file_path in file_paths:
        try:
            file_path = "./sources/" + file_path
            logging.info("Uploading source file: [%s]", file_path)
            uploaded_file = genai.upload_file(path=file_path, display_name=file_path.rsplit('/', maxsplit=1)[-1])
            uploaded_files.append(uploaded_file)
            logging.info("Source file [%s] uploaded successfully", file_path)
        except Exception as e:
            logging.critical("Failed to upload PDF file [%s]: %s", file_path, e)
            raise
    logging.info("Uploaded %i files to Gemini AI", len(uploaded_files))

def query_documents(prompt):
    """Queries the uploaded PDFs with the given prompt."""
    formatted_prompt = f"Based solely on the information in the source documents, answer the following question using the same language: `{prompt}`"
    logging.debug("Generated prompt: [%s]", formatted_prompt)
    
    try:
        response = model.generate_content([*uploaded_files, formatted_prompt])
        logging.debug("Successfully retrieved response from Gemini API.")
        return response.text
    except Exception as e:
        logging.warning("Exception while generating answer: %s", e)
        raise

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    logging.info("Received /start command from user: %s", update.effective_user.id)
    await update.message.reply_text(
        "Hello\\! Send me a message with your question about the source documents that were provided, and I'll do my best to help you\\!\\.",
        parse_mode="MarkdownV2"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes user messages and replies with the PDF query result."""
    user_message = str(update.message.text)
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    logging.info("Received message from user [%s] from chat_id: [%s] content: [%s]", user_id, chat_id, user_message)

    if (chat_id > 0):
        # Message is coming from normal user
        user_message = user_message.strip()
    else:
        # Message is coming from a group
        if (not user_message.startswith(TELEGRAM_BOT_NAME)):
            # Ignore messages from groups if not directed to the bot
            logging.debug("Ignoring message from [%s] as it was not directed to the bot", user_id)
            return
        else:
            # Remove the bot name from the query
            user_message = user_message[len(TELEGRAM_BOT_NAME):].strip()

    # Send a placeholder message and get the message ID
    processing_message = await update.message.reply_text("Processing your request...")
    logging.debug("Sent placeholder message, waiting for AI to reply.")

    # Query the Gemini API with a limited number of attempts
    logging.debug("Querying sources with user message: %s", user_message)

    max_attempts = int(GOOGLE_API_MAX_ATTEMPTS)
    last_error = ""

    for i in range(max_attempts):
        try:
            logging.debug("Trying to request answer from Gemini AI, tentative %i out of %s", i + 1, max_attempts)
            # Request data from Gemini AI
            result = query_documents(user_message)
            logging.debug("Got a result from Gemini, passing it to the Telegram APIs")
            # Replace the placeholder message with the actual result
            await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, result)
            logging.info("Replied to user [%s] from chat_id: [%s] with answer from AI: [%s...]", user_id, chat_id, result[:100])
            return
        except Exception as e:
            last_error = f"Error retrieving answer from AI: {e}"
            logging.warning(last_error)
            
            if "service is temporarily unavailable" in str(e):
                # If service timeout, try again later
                await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, "The bot is thinking hard, please wait...")
                logging.debug("Waiting few seconds before next attempt")
                time.sleep(3)
            else:
                # Something bad happeneded and needs to be fixed
                logging.warning("Exiting the for loop due to an unhandled error")
                break

    logging.error("Error while processing message from user [%s]: %s", user_id, last_error)
    # Replace the placeholder message with an error message
    await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, "Sorry, something went wrong while processing your request, please try again later.")
    logging.debug("Updated message with error notification.")

def escape_markdown_v2(text):
    """
    Escapes special characters for Telegram's MarkdownV2 formatting.
    """
    escape_chars = r'[_*[\]()~`>#+\-=|{}.!]'
    return re.sub(escape_chars, r'\\\g<0>', text)

async def bot_edit_text(context, chat_id, message_id, text):
    """
    Edits a message using Telegram's MarkdownV2 with escaped characters.
    """
    logging.debug("Escaping markdown content")
    escaped_text = escape_markdown_v2(text)  # Escape special characters

    try:
        logging.debug("Sending edited message")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=escaped_text,
            parse_mode="MarkdownV2"
        )
    except Exception as ret_exception:
        logging.error(ret_exception)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="An error occurred, please try again later"
        )

def main():
    """Main routine of the robot"""
    logging.info("Starting the AI assistant bot...")

    try:
        # Load environment variables
        load_environment()

        # Prepare Gemini AI
        initialize_gemini()

        # Initialize the Telegram bot
        logging.debug("Building the Telegram bot")
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

        # Register handlers
        logging.debug("Registering the /start command handler")
        app.add_handler(CommandHandler("start", handle_start))
        logging.debug("Registering the messages handler")
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Run the bot
        logging.info("Initialization completed, bot is now running...")
        app.run_polling()

    except Exception as e:
        logging.critical("Bot encountered an error: %s", e)
        raise

    finally:
        logging.warning("Sleeping 5 seconds before exiting the bot")
        time.sleep(5)

if __name__ == "__main__":
    configure_logging()
    main()
