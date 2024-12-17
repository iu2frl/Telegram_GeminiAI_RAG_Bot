import os
import logging
import time
import asyncio
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
reloading_gemini = False

class GeminiModelCreationException(BaseException):
    """Used to identify errors from Gemini"""
    pass

class GeminiApiInitializeException(BaseException):
    """Used to identify initialization errors"""
    pass

class GeminiRagUploadException(BaseException):
    """Used to identify files upload errors"""
    pass

class GeminiFilesListingException(BaseException):
    """Used to identify files upload errors"""
    pass

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

def gemini_initialize() -> None:
    """Initializes the Gemini AI parameters"""

    # Global variables
    global uploaded_files
    global model

    try:
        # Configure Gemini API
        logging.info("Configuring Gemini API from environment")
        genai.configure(api_key=GOOGLE_API_KEY)
        # Initialize the Gemini model
        logging.info("Initializing Gemini model [%s] from environment", GOOGLE_API_MODEL)
        model = genai.GenerativeModel(GOOGLE_API_MODEL)
    except Exception as e:
        logging.critical("Failed to initialize Gemini model: %s", e)
        raise GeminiApiInitializeException(e) from e

    try:
        # Get the list of uploaded files to the cloud
        logging.debug("Retrieving the list of files that are currently on the cloud")
        existing_files_on_cloud = genai.list_files()

        # Delete existing files
        for file_to_delete in existing_files_on_cloud:
            logging.info("Deleting old file [%s] uploaded on [%s] with hash [%s]", file_to_delete.name, file_to_delete.create_time, file_to_delete.sha256_hash)
            genai.delete_file(file_to_delete.name)
            logging.debug("File [%s] was deleted", file_to_delete.name)
    except Exception as e:
        logging.error("Failed to delete existing files on the cloud: %s", e)

    # List of file paths to upload as source
    try:
        logging.debug("Fetching all files in the sources folder")
        source_file_paths = list_files_in_folder("./sources")  # Add your file paths here
        logging.info("Found %i files in sources folder", len(source_file_paths))
    except Exception as e:
        logging.critical("Cannot retrieve documents from sources folder, error: %s", e)
        raise GeminiFilesListingException(e) from e

    # Make sure list is empty in case of new uploads
    uploaded_files.clear()

    # Upload each file and store the uploaded file references
    for source_file in source_file_paths:
        try:
            source_file = "./sources/" + source_file
            logging.info("Uploading source file: [%s]", source_file)
            uploaded_file = genai.upload_file(path=source_file, display_name=source_file.rsplit('/', maxsplit=1)[-1])
            uploaded_files.append(uploaded_file)
            logging.info("Source file [%s] uploaded successfully. Expire date: [%s]", source_file, uploaded_file.expiration_time)
        except Exception as e:
            logging.critical("Failed to upload PDF file [%s]: %s", source_file, e)
            raise
    if len(uploaded_files) > 0:
        logging.info("Uploaded %i files to Gemini AI", len(uploaded_files))
    else:
        raise GeminiRagUploadException("No valid files could be uploaded to Gemini AI")

async def gemini_query_sources(user_request):
    """Queries the uploaded PDFs with the given prompt."""
    ai_prompt = f"You are `{TELEGRAM_BOT_NAME}`, a chatbot that can only answer to users request based solely on the source documents. Reply to the following message using the same language: `{user_request}`"
    logging.debug("Generated prompt: [%s]", ai_prompt)

    try:
        # Create the model
        model_config = {
            "candidate_count": 1,
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 4096,
            "response_mime_type": "text/plain",
        }

        response = await model.generate_content_async([*uploaded_files, ai_prompt], generation_config=model_config)
        response_text = response.text.strip()
        logging.info("Successfully retrieved [%i] characters response from Gemini API", len(response_text))
        return response_text
    except Exception as e:
        logging.warning("Exception while generating answer: %s", e)
        raise GeminiModelCreationException(e) from e

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    logging.info("Received /start command from user: %s", update.effective_user.id)
    await update.message.reply_text(
        "Hello! Send me a message with your question about Olliter products, and I'll do my best to help you!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes user messages and replies with the PDF query result."""
    user_message_content = str(update.message.text)
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    logging.debug("Received message from user [%s] from chat_id: [%s]", user_id, chat_id)

    if (chat_id > 0):
        # Message is coming from normal user
        user_message_content = user_message_content
    else:
        # Message is coming from a group
        if (not user_message_content.startswith(TELEGRAM_BOT_NAME)):
            # Ignore messages from groups if not directed to the bot
            logging.debug("Ignoring message from group [%s] by user [%s] as it was not directed to the bot", chat_id, user_id)
            return
        else:
            # Remove the bot name from the query
            user_message_content = user_message_content[len(TELEGRAM_BOT_NAME):]

    logging.info("Processing valid message from user [%s] from chat_id: [%s]", user_id, chat_id)
    logging.debug("Message content: [%s]", user_message_content)

    # Send the cleaned request to the AI
    await bot_reply_to_message(update, context, user_message_content.strip())

async def bot_reply_to_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message_content: str):
    """
    This routine handles the cleaned request from the user and passes is to the Gemini APIs.
    Result is then sent to the user
    """
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    
    # Avoid processing messages if Gemini APIs are restarting
    global reloading_gemini

    # Send a placeholder message and get the message ID
    processing_message = await update.message.reply_text("Processing your request...")
    logging.debug("Sent placeholder message, waiting for AI to reply.")

    if (reloading_gemini):
        # If the Gemini API is being reloaded, wait for it to complete
        logging.info("Gemini API is being reloaded, waiting for it to complete.")
        await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, "The source files on the server are being updated, please wait...")
        while (reloading_gemini):
            await asyncio.sleep(1)
    
    # Query the Gemini API with a limited number of attempts
    logging.debug("Querying sources with user message: %s", user_message_content)

    max_attempts = int(GOOGLE_API_MAX_ATTEMPTS)
    last_error = ""

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
            return
        except GeminiModelCreationException as gemini_error:
            last_error = f"Error retrieving answer from AI: {gemini_error}"
            logging.error(last_error)
            error_code = 0
            telegram_error_message = "Please wait..."
            try:
                error_code = int(str(gemini_error).split(' ', maxsplit=1)[0])
                logging.warning("Error code %i. Waiting few seconds before next attempt", error_code)
                if 500 <= error_code < 600:
                    # If service timeout, try again later
                    telegram_error_message = "The bot is thinking hard, but he will be back soon, please wait..."
                elif 400 <= error_code < 500:
                    # For some reason we cannot connect load the files (permission error) - Files are probably expired
                    telegram_error_message = "The bot is having some hard time finding the right book from the shelf, please wait..."
                    if error_code == 403:
                        # If permission denied, files are expired, reload them
                        logging.warning("Files might be expired, need to reload them")
                        try:
                            reloading_gemini = True
                            gemini_initialize()
                        except Exception as gemini_init_exception:
                            logging.error("Failed to reload files, error: %s", gemini_init_exception)
                        finally:
                            reloading_gemini = False
                else:
                    # Something bad happeneded and needs to be fixed
                    logging.warning("Exiting the for loop due to an unhandled error: %s", gemini_error)
                    break
            except ValueError:
                # Cannot get the server error from Gemini
                logging.warning("Error code not found in Gemini error message: %s", gemini_error)
                telegram_error_message = "Unexpected server error, please trying again later."
            finally:
                logging.debug("Sending the error message to Telegram chat: [%s]", telegram_error_message)
                await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, telegram_error_message)
        except Exception as generic_exception:
            telegram_error_message = "Unexpected server error."
            logging.error("Unexpected error occurred while querying Gemini API: %s", generic_exception)
            await bot_edit_text(context, processing_message.chat_id, processing_message.message_id, telegram_error_message)
        finally:
            await asyncio.sleep(3)

    logging.error("Error while creating an answer for user [%s]: %s", user_id, last_error)
    # Replace the placeholder message with an error message
    await bot_send_message(context, processing_message.chat_id, "Sorry, something went wrong while processing your request, please try again later.")
    logging.debug("Updated message with error notification.")

async def bot_edit_text(context, chat_id, message_id, text: str):
    """
    Edits the message with the content of the file.
    """
    logging.debug("Stripping bot answer")
    escaped_text = text.strip()

    try:
        logging.debug("Sending edited message")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=escaped_text
        )
    except Exception as ret_exception:
        logging.error(ret_exception)
        await bot_send_message(context, chat_id, "An error occurred, please try again later")

async def bot_send_message(context, chat_id, message):
    """Send a message to the user"""
    await context.bot.send_message(chat_id, message)

def main():
    """Main routine of the robot"""
    logging.info("Starting the AI assistant bot...")

    try:
        # Load environment variables
        load_environment()

        # Prepare Gemini AI
        gemini_initialize()

        # Initialize the Telegram bot
        logging.debug("Building the Telegram bot")
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()

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
