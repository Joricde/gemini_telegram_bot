import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")
