"""Shared runtime state across modules."""

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
uploaded_files = []
GEMINI_CLIENT = None
