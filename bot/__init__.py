import os
import sys
import yaml
from dotenv import load_dotenv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Load .env file ---
# Looks for .env in the project root
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    # print(f"Loaded .env file from: {dotenv_path}") # For debugging
else:
    # Fallback if .env is not found, can issue a warning or rely on environment
    # print(f"Warning: .env file not found at {dotenv_path}. Relying on system environment variables.", file=sys.stderr)
    pass # Or raise an error if .env is critical

# --- Environment Variables (with defaults if not set) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'bot.db'}") # Default to data/bot.db
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

# --- Load app_config.yml ---
APP_CONFIG_PATH = PROJECT_ROOT / "config" / "app_config.yml"
APP_CONFIG = {}
try:
    with open(APP_CONFIG_PATH, "r", encoding="utf-8") as f:
        APP_CONFIG = yaml.safe_load(f)
    if APP_CONFIG is None: # Handle empty file case
        APP_CONFIG = {}
        # print(f"Warning: {APP_CONFIG_PATH} is empty. Using empty APP_CONFIG.", file=sys.stderr)
except FileNotFoundError:
    print(f"Error: Application config file not found at {APP_CONFIG_PATH}. Exiting.", file=sys.stderr)
    # sys.exit(1) # Or handle more gracefully depending on how critical it is
except yaml.YAMLError as e:
    print(f"Error: Could not parse application config file {APP_CONFIG_PATH}: {e}. Exiting.", file=sys.stderr)
    # sys.exit(1)

# --- Load prompts.yml ---
PROMPTS_CONFIG_PATH = PROJECT_ROOT / "config" / "prompts.yml"
PROMPTS_CONFIG = {}
try:
    with open(PROMPTS_CONFIG_PATH, "r", encoding="utf-8") as f:
        PROMPTS_CONFIG = yaml.safe_load(f)
    if PROMPTS_CONFIG is None: # Handle empty file case
        PROMPTS_CONFIG = {}
        # print(f"Warning: {PROMPTS_CONFIG_PATH} is empty. Using empty PROMPTS_CONFIG.", file=sys.stderr)
except FileNotFoundError:
    print(f"Error: Prompts config file not found at {PROMPTS_CONFIG_PATH}. Exiting.", file=sys.stderr)
    # sys.exit(1)
except yaml.YAMLError as e:
    print(f"Error: Could not parse prompts config file {PROMPTS_CONFIG_PATH}: {e}. Exiting.", file=sys.stderr)
    # sys.exit(1)


# --- Validate critical configurations ---
if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN is not set. Please set it in your .env file or environment.", file=sys.stderr)
    # sys.exit(1) # Critical, bot cannot run

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY is not set. Please set it in your .env file or environment.", file=sys.stderr)
    # sys.exit(1) # Critical, bot cannot use Gemini

# --- Expose configurations for other modules to import ---
# Example: from bot import TELEGRAM_BOT_TOKEN, APP_CONFIG, PROMPTS_CONFIG

# You might want to structure access to APP_CONFIG sections for clarity, e.g.:
GEMINI_SETTINGS = APP_CONFIG.get("gemini_settings", {})
DEFAULT_BOT_BEHAVIOR = APP_CONFIG.get("default_bot_behavior", {})
LOGGING_CONFIG = APP_CONFIG.get("logging", {})
DATABASE_CONFIG = APP_CONFIG.get("database", {}) # Though DATABASE_URL from .env might be primary

# --- Simple test print (remove in production) ---
if __name__ == '__main__':
    print("--- Configuration Loaded ---")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Telegram Bot Token: {'Loaded' if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
    print(f"Gemini API Key: {'Loaded' if GEMINI_API_KEY else 'NOT SET'}")
    print(f"Database URL: {DATABASE_URL}")
    print(f"HTTP Proxy: {HTTP_PROXY if HTTP_PROXY else 'Not set'}")
    print(f"HTTPS Proxy: {HTTPS_PROXY if HTTPS_PROXY else 'Not set'}")
    print("\n--- App Config ---")
    # print(yaml.dump(APP_CONFIG, indent=2, allow_unicode=True)) # Pretty print YAML
    print(f"  Default Base Model: {GEMINI_SETTINGS.get('default_base_model')}")
    print(f"  Logging Level: {LOGGING_CONFIG.get('level')}")
    print("\n--- Prompts Config (First 2 entries) ---")
    for i, (key, value) in enumerate(PROMPTS_CONFIG.items()):
        if i < 2:
            print(f"  Prompt Key: {key}, Name: {value.get('name')}")
        else:
            break
    print(f"  Total Prompts Loaded: {len(PROMPTS_CONFIG)}")
