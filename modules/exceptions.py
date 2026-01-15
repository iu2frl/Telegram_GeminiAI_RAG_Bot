# Custom exceptions
class GeminiModelCreationException(BaseException):
    """Used to identify errors from Gemini"""


class GeminiApiInitializeException(BaseException):
    """Used to identify initialization errors"""


class GeminiRagUploadException(BaseException):
    """Used to identify files upload errors"""


class GeminiFilesListingException(BaseException):
    """Used to identify files upload errors"""


class GeminiQueryException(BaseException):
    """Used to identify files expired errors"""


class TelegramFloodControlException(Exception):
    """Used to identify Telegram flood control errors that require container restart"""
