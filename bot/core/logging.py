# logging.py

import logging
import sys

logger = logging.getLogger("gemini_telegram_bot")

logger.setLevel(logging.DEBUG) # Or logging.INFO, as you need

logger.propagate = False
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
console_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(console_handler)


logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
