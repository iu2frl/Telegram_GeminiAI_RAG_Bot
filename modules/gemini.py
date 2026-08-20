"""
Gemini AI integration module.
"""

import logging
import os
import mimetypes
from datetime import datetime, timezone

from google import genai

from modules import state
from modules.exceptions import (
    GeminiApiInitializeException,
    GeminiFilesListingException,
    GeminiQueryException,
    GeminiRagUploadException,
)
from modules.repos import clone_or_pull_repo, list_files_in_folder
from modules.state import GenAiModel
from modules.prompt_security import build_safe_prompt, validate_prompt_safety

mimetypes.add_type("text/markdown", ".md")


def gemini_initialize() -> None:
    """Initializes the Gemini AI parameters"""

    try:
        # Configure Gemini API
        logging.info("Configuring Gemini API from environment")
        state.GEMINI_CLIENT = genai.Client(api_key=state.GOOGLE_API_KEY)
        # Initialize the Gemini model
        logging.info("Initializing Gemini client for model [%s]", state.GOOGLE_API_MODEL)
    except Exception as e:
        logging.critical("Failed to initialize Gemini client: %s", e)
        raise GeminiApiInitializeException(e) from e

    try:
        # Get the list of uploaded files to the cloud
        logging.debug("Retrieving the list of files that are currently on the cloud")
        existing_files_on_cloud = state.GEMINI_CLIENT.files.list()

        # Delete existing files
        for file_to_delete in existing_files_on_cloud:
            logging.info("Deleting old file [%s] uploaded on [%s] with hash [%s]", file_to_delete.name, file_to_delete.create_time, file_to_delete.sha256_hash)
            state.GEMINI_CLIENT.files.delete(name=str(file_to_delete.name))
            logging.debug("File [%s] was deleted", file_to_delete.name)
    except Exception as e:
        logging.error("Failed to delete existing files on the cloud: %s", e)

    # Clone or pull the repository
    clone_or_pull_repo()

    # List of file paths to upload as source
    try:
        logging.debug("Fetching all files in the cloned repository")
        source_file_paths = list_files_in_folder(state.LOCAL_REPO_PATH)
        logging.info("Found %i files in cloned repository", len(source_file_paths))
    except Exception as e:
        logging.critical("Cannot retrieve documents from cloned repository, error: %s", e)
        raise GeminiFilesListingException(e) from e

    # Make sure list is empty in case of new uploads
    state.UploadedFiles.clear()

    # Upload each file and store the uploaded file references
    for source_file in source_file_paths:
        try:
            logging.info("Uploading source file: [%s]", source_file)
            mime_type = mimetypes.guess_type(source_file)[0] or "text/markdown"
            uploaded_file = state.GEMINI_CLIENT.files.upload(
                file=source_file,
                config={
                    "display_name": os.path.basename(source_file),
                    "mime_type": mime_type,
                },
            )
            state.UploadedFiles.append(uploaded_file)
            logging.info("Source file [%s] uploaded successfully. Expire date: [%s]", source_file, uploaded_file.expiration_time)
        except Exception as e:
            logging.warning("Failed to upload file [%s]: %s", source_file, e)
    if len(state.UploadedFiles) > 0:
        logging.info("Uploaded %i files to Gemini AI", len(state.UploadedFiles))
    else:
        raise GeminiRagUploadException("No valid files could be uploaded to Gemini AI")


async def gemini_query_sources(user_request: str) -> str:
    """
    Queries the uploaded PDFs with the given prompt.
    Uses safe templating to prevent prompt injection attacks.
    """
    # Build safe prompt using Jinja2 templating (prevents injection attacks)
    prompt = build_safe_prompt(state.TELEGRAM_BOT_NAME, user_request)
    
    # Validate prompt safety (defense in depth)
    if not validate_prompt_safety(prompt, user_request):
        logging.warning("Prompt safety validation failed, but proceeding with caution")
    
    logging.debug("Generated prompt with %i characters", len(prompt))

    try:
        if (state.GOOGLE_API_MODEL.lower() == "auto") or (state.GOOGLE_API_MODEL.strip() == ""):
            response_text = await gemini_generate_content_auto_model(prompt)
        else:
            response_text = await gemini_generate_content_fixed_model(prompt)

        logging.info("Successfully retrieved [%i] characters response from Gemini API", len(response_text))
        return response_text
    except Exception as e:
        logging.error("Failed to query Gemini API: %s", e)
        raise GeminiQueryException(e) from e


async def gemini_generate_content_fixed_model(user_request: str) -> str:
    """Generates content using Gemini AI and custom settings."""

    response = ""

    try:
        logging.debug("Using fixed Gemini model [%s] for the request", state.GOOGLE_API_MODEL)
        response, token_count = await _gemini_generate_content(user_request, state.GOOGLE_API_MODEL)
        logging.info("Gemini API call to [%s] used %i tokens", state.GOOGLE_API_MODEL, token_count)
    except Exception as e:
        logging.error("Failed to generate content with fixed model: %s", e)
        raise GeminiQueryException(e) from e

    return response


async def gemini_generate_content_auto_model(user_request: str) -> str:
    """Generates content using Gemini AI with automatic model selection."""

    # Check if the model is available
    if not state.MODELS_LIST or len(state.MODELS_LIST) == 0:
        raise GeminiQueryException("No Gemini models are configured for automatic selection")

    model_to_use: GenAiModel | None = None

    for model in state.MODELS_LIST:
        if model.is_available():
            model_to_use = model
            break

    if not model_to_use:
        logging.warning("No Gemini model is currently available due to rate limiting")
        return "Service is currently unavailable due to high demand. Please try again later."

    logging.debug("Selected Gemini model [%s] for the request", model_to_use.name)
    request_timestamp = datetime.now(tz=timezone.utc)
    token_count = 0
    response = ""

    try:
        response, token_count = await _gemini_generate_content(user_request, model_to_use.name)
        logging.info("Gemini API call to [%s] used %i tokens", model_to_use.name, token_count)

    except Exception as e:
        logging.error("Failed to get response from Gemini API: %s", e)
        raise GeminiQueryException(e) from e

    finally:
        # Log the request for rate limiting
        model_to_use.add_request(timestamp=request_timestamp, token_count=token_count)
        logging.info("Model [%s] request log updated. RPM: [%i], TPM: [%i], RPD: [%i]",
                     model_to_use.name, model_to_use.get_rpm(), model_to_use.get_tpm(), model_to_use.get_rpd())

    return response

async def _gemini_generate_content(user_request: str, model: str) -> tuple[str, int]:
    """Generates content using Gemini AI and returns the response along with token count."""

    if state.GEMINI_CLIENT is None:
        raise GeminiApiInitializeException("Gemini client is not initialized")

    response = await state.GEMINI_CLIENT.aio.models.generate_content(model=model, contents=[*state.UploadedFiles, user_request], config=state.MODEL_CONFIG)

    # Get the number of tokens used
    token_count = 0
    if response.usage_metadata and response.usage_metadata.total_token_count:
        token_count = response.usage_metadata.total_token_count
        logging.debug("Gemini API used %i tokens", token_count)

    if not response or not response.text or len(response.text.strip()) <= 1:
        raise GeminiQueryException("Received empty response from Gemini API")

    return response.text.strip(), token_count
