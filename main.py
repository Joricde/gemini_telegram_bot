# main.py
from bot.telegram.app import run
from bot.core.logging import logger

if __name__ == "__main__":
    logger.info("Bot application starting...")
    try:
        run()
    except Exception as e:
        logger.critical(f"Bot application failed to start or crashed: {e}", exc_info=True)
    logger.info("Bot application has shut down.")

