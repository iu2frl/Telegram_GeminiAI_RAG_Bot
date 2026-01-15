import logging
import os
import mimetypes

from google import genai
from google.genai import types

from modules import state
from modules.exceptions import (
    GeminiApiInitializeException,
    GeminiFilesListingException,
    GeminiQueryException,
    GeminiRagUploadException,
)
from modules.repos import clone_or_pull_repo, list_files_in_folder

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
            state.GEMINI_CLIENT.files.delete(name=file_to_delete.name)
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
    state.uploaded_files.clear()

    # Upload each file and store the uploaded file references
    for source_file in source_file_paths:
        try:
            logging.info("Uploading source file: [%s]", source_file)
            mime_type = mimetypes.guess_type(source_file)[0] or "text/markdown"
            uploaded_file = state.GEMINI_CLIENT.files.upload(
                file=source_file,
                config={
                    'display_name': os.path.basename(source_file),
                    'mime_type': mime_type,
                }
            )
            state.uploaded_files.append(uploaded_file)
            logging.info("Source file [%s] uploaded successfully. Expire date: [%s]", source_file, uploaded_file.expiration_time)
        except Exception as e:
            logging.warning("Failed to upload file [%s]: %s", source_file, e)
    if len(state.uploaded_files) > 0:
        logging.info("Uploaded %i files to Gemini AI", len(state.uploaded_files))
    else:
        raise GeminiRagUploadException("No valid files could be uploaded to Gemini AI")


async def gemini_query_sources(user_request):
    """Queries the uploaded PDFs with the given prompt."""
    instruction = f"You are `{state.TELEGRAM_BOT_NAME}`, a chatbot that can only answer to users request based solely on the source documents. Reply to the following message using the same language, when returning LaTex formulas, try to translate them to simple text if possible."
    user_request = f"{instruction}:\n\n`{user_request}`"
    logging.debug("Generated prompt: [%s]", user_request)

    try:
        # Create the model config
        model_config = types.GenerateContentConfig(
            candidate_count=1,
            temperature=1,
            top_p=0.95,
            top_k=40,
            max_output_tokens=4096,
        )

        response = await state.GEMINI_CLIENT.aio.models.generate_content(
            model=state.GOOGLE_API_MODEL,
            contents=[*state.uploaded_files, user_request],
            config=model_config
        )
        response_text = response.text.strip()
        logging.info("Successfully retrieved [%i] characters response from Gemini API", len(response_text))
        return response_text
    except Exception as e:
        logging.error("Failed to query Gemini API: %s", e)
        raise GeminiQueryException(e) from e

