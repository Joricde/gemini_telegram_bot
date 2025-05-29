# gemini-telegram-bot/main.py

import asyncio
import importlib  # For dynamically importing handlers

from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, Defaults, CallbackQueryHandler

from bot import (
    TELEGRAM_BOT_TOKEN,
    # APP_CONFIG, # Not directly used in main after this refactor, but other modules use it
    PROMPTS_CONFIG,  # Used for initializing system prompts
    PROJECT_ROOT,
    GEMINI_SETTINGS  # Used for initializing system prompts
    # DEFAULT_BOT_BEHAVIOR, # Not directly used in main
    # LOGGING_CONFIG # Logging is set up by utils
)
from bot.utils import log
from bot.database import init_db, SessionLocal
from bot.database.crud import create_prompt as db_create_prompt  # Alias to avoid conflict
from bot.database.models import PromptType  # For initializing system prompts
from bot.gemini_service import GeminiService


# (main.py imports)
# ...
from bot.database import init_db, SessionLocal
# Alias existing imports if you keep them, or use the correct names directly
from bot.database.crud import create_prompt as db_create_prompt
from bot.database.crud import get_system_prompt_by_name # Correct function to import
from bot.database.models import PromptType
from bot.database import models as db_models # <<< ADD THIS LINE
# ...

# Import handlers from the new structure
from bot.telegram_adapter import base as base_handlers
from bot.telegram_adapter import commands as command_handlers
from bot.telegram_adapter import callbacks as callback_handlers



def ensure_data_directory():
    """Ensures the data directory (e.g., for SQLite) exists."""
    # Assuming DATABASE_URL points to a file within a 'data' subdirectory of PROJECT_ROOT
    # This logic might be more robust if DATABASE_URL's path is parsed,
    # but for default "sqlite:///./data/bot.db" this works if PROJECT_ROOT is parent of "data"
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Created data directory: {data_dir}")
        except OSError as e:
            log.error(f"Could not create data directory {data_dir}: {e}")


# (In main.py)
def initialize_system_prompts():
    """Loads prompts from prompts.yml into the database if they don't exist."""
    db = SessionLocal()
    try:
        log.info("Initializing system prompts from config into database...")
        default_gen_params = GEMINI_SETTINGS.get("default_generation_parameters", {})

        for key, prompt_data in PROMPTS_CONFIG.items():
            prompt_name = prompt_data.get("name", key)

            prompt_type_str = prompt_data.get("prompt_type", "private").upper()
            try:
                prompt_type_enum = PromptType[prompt_type_str]
            except KeyError:
                log.warning(f"Invalid prompt_type '{prompt_type_str}' for '{prompt_name}' in prompts.yml. Defaulting to PRIVATE.")
                prompt_type_enum = PromptType.PRIVATE

            # Use the correct function: get_system_prompt_by_name
            # This function already filters by is_system_default = True
            existing_system_prompt = get_system_prompt_by_name(db, name=prompt_name)

            # We also need to ensure it's the correct type if names can collide across types for system prompts
            # However, get_system_prompt_by_name doesn't filter by type, so an additional check might be good
            # if system prompts with the same name but different types are possible.
            # For now, let's assume system prompt names are unique regardless of type.
            # If a system prompt exists with this name, we check if its type matches.
            # If types can't collide for same-named system prompts, this check is simpler.

            found_and_correct_type = False
            if existing_system_prompt:
                if existing_system_prompt.prompt_type == prompt_type_enum:
                    found_and_correct_type = True
                else:
                    log.warning(f"System prompt '{prompt_name}' exists but with a different type "
                                f"(DB: {existing_system_prompt.prompt_type}, YML: {prompt_type_enum}). Will not create new one.")
                                # Or decide to create a new one if names are not unique across types for system prompts

            if not found_and_correct_type and not existing_system_prompt: # Simpler: if not existing_system_prompt (assuming names are unique for system prompts)
                                                                          # Let's assume for now that get_system_prompt_by_name is sufficient to check existence
                                                                          # and we don't have system prompts with same name but different types.
                                                                          # The primary check is just `if not existing_system_prompt:`

                # Simplified check:
                # if not get_system_prompt_by_name(db, name=prompt_name): # This would be simpler if name is globally unique for system prompts

                # Using the more specific check based on the query I wrote before for existing_system_prompt in main.py
                # This query was more robust:
                query = db.query(db_models.Prompt).filter(   # Use db_models here
                    db_models.Prompt.name == prompt_name,    # Use db_models here
                    db_models.Prompt.is_system_default == True,
                    db_models.Prompt.prompt_type == prompt_type_enum
                )
                already_exists_with_correct_type = query.first()


                if not already_exists_with_correct_type:
                    created = db_create_prompt( # Use aliased name
                        db=db,
                        name=prompt_name,
                        description=prompt_data.get("description"),
                        system_instruction=prompt_data.get("system_instruction", ""),
                        prompt_type=prompt_type_enum,
                        temperature=prompt_data.get("temperature", default_gen_params.get("temperature")),
                        top_p=prompt_data.get("top_p", default_gen_params.get("top_p")),
                        top_k=prompt_data.get("top_k", default_gen_params.get("top_k")),
                        max_output_tokens=prompt_data.get("max_output_tokens", default_gen_params.get("max_output_tokens")),
                        base_model_override=prompt_data.get("base_model_override"),
                        is_system_default=True
                    )
                    if created:
                        log.info(f"Added system prompt to DB: '{prompt_name}' (Type: {prompt_type_enum.value}, ID: {created.id})")
                    else:
                        log.error(f"Failed to add system prompt to DB: '{prompt_name}' (CRUD function returned None).")
                # else:
                #     log.debug(f"System prompt '{prompt_name}' (Type: {prompt_type_enum.value}) already exists.")

    except Exception as e:
        log.error(f"Error initializing system prompts: {e}", exc_info=True)
    finally:
        db.close()


async def post_init(application: Application):
    """Sets bot commands after initialization."""
    log.info("Running post_init hook...")
    await application.bot.set_my_commands([
        ("start", "🚀 开始/帮助"),
        ("help", "ℹ️ 显示帮助信息"),
        ("my_prompts", "📚 查看和选择私人角色"),
        ("upload_prompt", "✍️ 创建新的私人角色"),
        # Add /edit_prompt and /delete_prompt here if they become direct commands
        # For now, they are initiated via buttons from /my_prompts
        ("cancel", "❌ 取消当前操作"),
        # Add group commands later, e.g. /group_mode, /set_group_role
    ])
    log.info("Bot commands set.")


async def main():
    log.info("Starting bot application...")

    if not TELEGRAM_BOT_TOKEN:
        log.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    ensure_data_directory()  # Ensure data directory exists for DB
    init_db()  # Initialize database (create tables if not exist)
    log.info("Database initialized.")

    initialize_system_prompts()  # Load system prompts from YML to DB
    log.info("System prompts initialized.")

    gemini_service = GeminiService()
    log.info("GeminiService initialized.")

    # Set default parse mode for replies
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .defaults(defaults)
        .post_init(post_init)  # Function to run after bot is initialized
        .build()
    )

    # Store GeminiService in bot_data for access in handlers
    application.bot_data["gemini_service"] = gemini_service
    log.info("Telegram Application built and GeminiService stored in bot_data.")

    # --- Register Handlers ---
    # Basic handlers from base.py
    application.add_handler(CommandHandler("start", base_handlers.start_command_handler))
    application.add_handler(CommandHandler("help", base_handlers.help_command_handler))

    # Command Handlers from commands.py
    application.add_handler(CommandHandler("my_prompts", command_handlers.my_prompts_command_handler))

    # Callback Query Handlers from callbacks.py
    # This handler manages multiple patterns for private prompt actions.
    # The pattern here should be broad enough or specific if this handler only does one thing.
    # Our private_prompts_callback_handler handles various "pr_" prefixed callbacks.
    application.add_handler(CallbackQueryHandler(
        callback_handlers.private_prompts_callback_handler,
        pattern="^pr_"  # Catches all callbacks starting with "pr_"
    ))

    # General Private Message Handler from base.py
    # This should generally be one of the last message handlers added for private chats
    # to ensure commands and conversation states are processed first.
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        base_handlers.private_message_handler
    ))

    # Error Handler from base.py
    application.add_error_handler(base_handlers.error_handler)

    log.info("All bot handlers registered.")

    log.info("Bot is starting to poll for updates...")
    try:
        await application.initialize()  # Initializes the bot, dispatcher, etc.
        await application.updater.start_polling()  # type: ignore # Start polling for updates
        await application.start()  # Start the application (starts the updater)
        log.info("Bot is running.")
        # Keep the application running until interrupted
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour, or use a more robust keep-alive
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot shutting down via interrupt...")
    except Exception as e:
        log.critical(f"Bot failed to run: {e}", exc_info=True)
    finally:
        log.info("Attempting to gracefully stop the bot...")
        if application.updater and application.updater.running:  # type: ignore
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        log.info("Bot has been shut down.")


if __name__ == "__main__":
    asyncio.run(main())

