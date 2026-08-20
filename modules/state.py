"""Shared runtime state across modules."""

from datetime import datetime, timezone
from google.genai import Client, types

# Global configuration
GOOGLE_API_KEY = ""
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_BOT_NAME = ""
GOOGLE_API_MODEL = ""
GOOGLE_API_MAX_ATTEMPTS = ""
REPO_URL = ""
TELEGRAM_RESTART_DELAY_SECONDS = ""

# State variables
LOCAL_REPO_PATH = "./sources"
BUILD_DATE = ""

# Working variables
RELOADING_GEMINI = False
UploadedFiles: list[types.File] = []
GEMINI_CLIENT: Client | None = None

# Model configuration
MODEL_CONFIG = types.GenerateContentConfig(
    candidate_count=1,
    temperature=1,
    top_p=0.95,
    top_k=40,
    max_output_tokens=4096,
)


class GenAiRequest:
    """Represents a GenAI request with timestamp and token count."""

    timestamp: datetime
    token_count: int

    def __init__(self, timestamp: datetime, token_count: int):
        self.timestamp = timestamp
        self.token_count = token_count


class GenAiModel:
    """Represents a GenAI model with rate limiting."""

    name: str
    max_rpm: int  # Maximum number of requests per minute
    max_tpm: int  # Maximum number of input tokens per minute
    max_rpd: int  # Maximum number of requests per day

    def __init__(self, name: str, max_rpm: int, max_tpm: int, max_rpd: int):
        self.name = name
        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self.max_rpd = max_rpd
        self.requests: list[GenAiRequest] = []

    def add_request(self, timestamp: datetime | None = None, token_count: int = 0):
        """Add a request timestamp to the model's request log."""
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        self.requests.append(GenAiRequest(timestamp, token_count))

    def is_available(self, timestamp: datetime | None = None) -> bool:
        """Check if the model can accept more requests based on rate limits."""

        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)

        # Clean up old requests
        self.requests = [req for req in self.requests if (timestamp - req.timestamp).total_seconds() < 86400]  # 24 hours

        # Calculate requests in the last minute, hour, and day
        requests_last_minute = [req for req in self.requests if (timestamp - req.timestamp).total_seconds() < 60]
        requests_last_hour = [req for req in self.requests if (timestamp - req.timestamp).total_seconds() < 3600]
        requests_last_day = self.requests  # Already filtered above

        return len(requests_last_minute) < self.max_rpm and len(requests_last_hour) < self.max_tpm and len(requests_last_day) < self.max_rpd

    def get_rpm(self, timestamp: datetime | None = None) -> int:
        """Get the number of requests in the last minute."""
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        return len([req for req in self.requests if (timestamp - req.timestamp).total_seconds() < 60])

    def get_tpm(self, timestamp: datetime | None = None) -> int:
        """Get the number of tokens in the last hour."""
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        return sum(req.token_count for req in self.requests if (timestamp - req.timestamp).total_seconds() < 3600)

    def get_rpd(self, timestamp: datetime | None = None) -> int:
        """Get the number of requests in the last day."""
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        return len([req for req in self.requests if (timestamp - req.timestamp).total_seconds() < 86400])

# Usage limits based on https://aistudio.google.com/usage?timeRange=last-7-days
MODELS_LIST: list[GenAiModel] = [
    GenAiModel("gemini-3.1-flash-lite", max_rpm=15, max_tpm=250000, max_rpd=500),
    GenAiModel("gemini-3.5-flash", max_rpm=5, max_tpm=250000, max_rpd=20),
    GenAiModel("gemini-3-flash", max_rpm=5, max_tpm=250000, max_rpd=20)
]
