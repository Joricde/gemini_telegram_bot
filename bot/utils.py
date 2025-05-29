import logging
import logging.handlers
import os
import sys
import yaml
from telegram import Update, ChatMember # Add ChatMember
from telegram.ext import ContextTypes # Add ContextTypes
from telegram.error import TelegramError # For catching potential errors
# --- Configuration Loading (Simplified for this module) ---
# In a real scenario, a shared config loader module might be preferred.
_config = {}
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # gemini-telegram-bot directory
_config_path = os.path.join(_project_root, "config", "app_config.yml")

try:
    with open(_config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
except FileNotFoundError:
    print(f"Warning: Logging config file not found at {_config_path}. Using default logging settings.", file=sys.stderr)
except yaml.YAMLError as e:
    print(f"Warning: Error parsing logging config file {_config_path}: {e}. Using default logging settings.", file=sys.stderr)

# --- Extract Logging Config with Defaults ---
_logging_config = _config.get("logging", {})
LOG_LEVEL = _logging_config.get("level", "INFO").upper()
LOG_FILE_PATH_CONFIG = _logging_config.get("file_path", "logs/bot.log") # Relative to project root
LOG_MAX_BYTES = _logging_config.get("max_bytes", 10 * 1024 * 1024) # Default 10MB
LOG_BACKUP_COUNT = _logging_config.get("backup_count", 5) # Default 5 backup files

# Construct absolute log file path
LOG_FILE_PATH = os.path.join(_project_root, LOG_FILE_PATH_CONFIG)

# Ensure logs directory exists
_log_dir = os.path.dirname(LOG_FILE_PATH)
if not os.path.exists(_log_dir):
    try:
        os.makedirs(_log_dir)
    except OSError as e:
        print(f"Warning: Could not create log directory {_log_dir}: {e}. File logging might fail.", file=sys.stderr)


# --- Logger Setup ---
def setup_logger(name="gemini_bot"):
    """
    Configures and returns a logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    logger.propagate = False # Prevents log duplication if root logger is also configured

    # Avoid adding handlers if they already exist (e.g., during reloads)
    if logger.hasHandlers():
        return logger

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(LOG_LEVEL) # Console can have its own level if needed
    logger.addHandler(console_handler)

    # File Handler (RotatingFileHandler)
    if _log_dir and os.path.exists(_log_dir): # Only add file handler if directory is usable
        file_handler = logging.handlers.RotatingFileHandler(
            filename=LOG_FILE_PATH,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(LOG_LEVEL) # File can also have its own level
        logger.addHandler(file_handler)
    else:
        logger.warning(f"Log directory '{_log_dir}' does not exist or is not accessible. File logging is disabled.")

    return logger

# --- Get a pre-configured logger instance ---
# This allows other modules to simply import 'log' from this utils module.
log = setup_logger()


async def is_user_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user who sent the message is an administrator or creator of the group."""
    if not update.effective_chat or not update.effective_user:
        return False

    # Only applicable for group/supergroup chats
    if update.effective_chat.type not in ["group", "supergroup"]:
        return False

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        chat_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            log.debug(f"User {user_id} is an admin/creator in chat {chat_id} (Status: {chat_member.status}).")
            return True
        log.debug(f"User {user_id} is not an admin/creator in chat {chat_id} (Status: {chat_member.status}).")
        return False
    except TelegramError as e:
        log.error(f"TelegramError while checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False  # Assume not admin on error
    except Exception as e:
        log.error(f"Unexpected error while checking admin status for user {user_id} in chat {chat_id}: {e}",
                  exc_info=True)
        return False



if __name__ == '__main__':
    # Example usage:
    log.debug("This is a debug message.")
    log.info("This is an info message.")
    log.warning("This is a warning message.")
    log.error("This is an error message.")
    log.critical("This is a critical message.")

    print(f"Logging configured with level: {LOG_LEVEL}")
    print(f"Log file path: {LOG_FILE_PATH}")