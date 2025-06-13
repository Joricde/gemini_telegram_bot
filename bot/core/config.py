# bot/core/config.py
import yaml
from pathlib import Path
from typing import List, Dict, Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Define the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent


# --- Nested Pydantic Models for Type Safety ---
class TelegramBotConfig(BaseModel):
    session_timeout_seconds: int = 1800
    group_reply_probability: float = 0.2
    log_level: str = "INFO"
    group_chat_header: str = ""  # A default value


class GeminiConfig(BaseModel):
    model_name: str = "gemini-2.5-flash"


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///data/bot_database.db"
    echo: bool = False


class AppConfig(BaseModel):
    database: DatabaseConfig
    gemini: GeminiConfig
    telegram_bot: TelegramBotConfig


# --- Main Settings Class ---
class Settings(BaseSettings):
    """
    Main settings class that loads from .env and is then populated from YAML files.
    """
    # These fields are loaded directly from the .env file
    telegram_bot_token: str
    gemini_api_key: str
    admin_user_ids: List[int] = Field(default_factory=list)

    # These fields will be populated from our YAML data
    app: AppConfig
    prompts: Dict[str, Any]

    # Configure Pydantic to load from the .env file
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding='utf-8',
        extra='ignore'  # Ignore extra fields that might come from os environment
    )


def load_yaml_configs() -> Dict[str, Any]:
    """A simple helper function to load our YAML configs."""
    config_dir = PROJECT_ROOT / "config"

    with open(config_dir / "app_config.yml", 'r', encoding='utf-8') as f:
        app_data = yaml.safe_load(f)

    with open(config_dir / "prompts.yml", 'r', encoding='utf-8') as f:
        prompts_data = yaml.safe_load(f)

    return {"app": app_data, "prompts": prompts_data}


# --- Initialization Logic ---

# 1. Load the data from our YAML files first
yaml_data = load_yaml_configs()

# 2. Initialize the Settings object.
# Pydantic-settings will automatically load from the .env file,
# and then we explicitly pass the loaded YAML data.
# The `**` operator unpacks our dictionary into keyword arguments.
settings = Settings(**yaml_data)

# --- Post-config setup ---
# Ensure the data directory for SQLite exists
db_path = Path(settings.app.database.url.split(":///")[1])
db_path.parent.mkdir(parents=True, exist_ok=True)
