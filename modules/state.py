"""Shared runtime state across modules."""
from google.genai import Client, types

# Global configuration/state values
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_BOT_NAME = ""
GOOGLE_API_KEY = ""
GOOGLE_API_MODEL = ""
GOOGLE_API_MAX_ATTEMPTS = ""
REPO_URL = ""
LOCAL_REPO_PATH = "./sources"
MODEL = None
BUILD_DATE = ""
TELEGRAM_RESTART_DELAY_SECONDS = ""

# Working variables
RELOADING_GEMINI = False
UploadedFiles: list[types.File] = []
GEMINI_CLIENT: Client = Client()
