import logging

def configure_logging() -> None:
    """Configure logging options"""
    logging.basicConfig(
        level=logging.INFO,  # Set to DEBUG for detailed logs; use INFO in production
        format="%(asctime)s - %(levelname)s - %(funcName)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set specific modules to WARNING level
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
