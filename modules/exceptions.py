"""
Module defining custom exceptions for Gemini AI operations.
"""

# Custom exceptions
class GeminiApiInitializeException(Exception):
    """Used to identify initialization errors"""


class GeminiRagUploadException(Exception):
    """Used to identify files upload errors"""


class GeminiFilesListingException(Exception):
    """Used to identify files upload errors"""


class GeminiQueryException(Exception):
    """Used to identify files expired errors"""


class TelegramFloodControlException(Exception):
    """Used to identify Telegram flood control errors that require container restart"""
