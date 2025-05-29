# gemini-telegram-bot/main.py

import asyncio
# import importlib # For dynamically importing handlers # Not strictly needed for this change

from telegram import Update  # Added Update for type hinting in new handlers
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,  # Make sure filters is imported
    Defaults,
    CallbackQueryHandler,
    ConversationHandler  # <-- Add ConversationHandler
)
from telegram.ext import ContextTypes  # Added ContextTypes for new handlers

from bot import (
    TELEGRAM_BOT_TOKEN,
    PROMPTS_CONFIG,
    PROJECT_ROOT,
    GEMINI_SETTINGS
)
from bot.utils import log
from bot.database import init_db, SessionLocal
from bot.database.crud import create_prompt as db_create_prompt
from bot.database.crud import get_system_prompt_by_name
from bot.database.models import PromptType
from bot.database import models as db_models
from bot.gemini_service import GeminiService

# Import handlers from the new structure
from bot.telegram_adapter import base as base_handlers
# Import specific command handlers, including the new cancel_command_handler
from bot.telegram_adapter import commands as command_handlers
from bot.telegram_adapter import callbacks as callback_handlers

# Import states and processing functions from prompt_manager
from bot.message_processing import prompt_manager  # <-- Add this


# Explicitly import states if needed, though accessing via prompt_manager.STATE_NAME is fine
# from bot.message_processing.prompt_manager import UPLOAD_PRIVATE_INSTRUCTION, UPLOAD_PRIVATE_NAME, EDIT_PRIVATE_INSTRUCTION


# ... (ensure_data_directory, initialize_system_prompts, post_init functions remain the same) ...
# Make sure they are defined as in your existing main.py file. For brevity, I'm omitting them here.

def ensure_data_directory():
    """Ensures the data directory (e.g., for SQLite) exists."""
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Created data directory: {data_dir}")
        except OSError as e:
            log.error(f"Could not create data directory {data_dir}: {e}")


def initialize_system_prompts():
    """Loads prompts from prompts.yml into the database if they don't exist."""
    db = SessionLocal()
    try:
        log.info("Initializing system prompts from config into database...")
        default_gen_params = GEMINI_SETTINGS.get("default_generation_parameters", {})

        for key, prompt_data_item in PROMPTS_CONFIG.items():
            prompt_name = prompt_data_item.get("name", key)
            prompt_type_str = prompt_data_item.get("prompt_type", "private").upper()
            try:
                prompt_type_enum = PromptType[prompt_type_str]
            except KeyError:
                log.warning(
                    f"Invalid prompt_type '{prompt_type_str}' for '{prompt_name}' in prompts.yml. Defaulting to PRIVATE.")
                prompt_type_enum = PromptType.PRIVATE

            query = db.query(db_models.Prompt).filter(
                db_models.Prompt.name == prompt_name,
                db_models.Prompt.is_system_default == True,
                db_models.Prompt.prompt_type == prompt_type_enum
            )
            already_exists_with_correct_type = query.first()

            if not already_exists_with_correct_type:
                created = db_create_prompt(
                    db=db,
                    name=prompt_name,
                    description=prompt_data_item.get("description"),
                    system_instruction=prompt_data_item.get("system_instruction", ""),
                    prompt_type=prompt_type_enum,
                    temperature=prompt_data_item.get("temperature", default_gen_params.get("temperature")),
                    top_p=prompt_data_item.get("top_p", default_gen_params.get("top_p")),
                    top_k=prompt_data_item.get("top_k", default_gen_params.get("top_k")),
                    max_output_tokens=prompt_data_item.get("max_output_tokens",
                                                           default_gen_params.get("max_output_tokens")),
                    base_model_override=prompt_data_item.get("base_model_override"),
                    is_system_default=True
                )
                if created:
                    log.info(
                        f"Added system prompt to DB: '{prompt_name}' (Type: {prompt_type_enum.value}, ID: {created.id})")
                else:
                    log.error(f"Failed to add system prompt to DB: '{prompt_name}' (CRUD function returned None).")
    except Exception as e:
        log.error(f"Error initializing system prompts: {e}", exc_info=True)
    finally:
        db.close()


async def post_init(application: Application):
    log.info("Running post_init hook...")
    await application.bot.set_my_commands([
        ("start", "🚀 开始/帮助"),
        ("help", "ℹ️ 显示帮助信息"),
        ("my_prompts", "📚 查看和选择私人角色"),
        ("upload_prompt", "✍️ 创建新的私人角色"),
        ("set_prompt", "💡 设置当前私人角色"),  # Added /set_prompt
        ("cancel", "❌ 取消当前操作"),
    ])
    log.info("Bot commands set.")


# --- Conversation Step Handlers (glue between ConversationHandler and prompt_manager) ---
async def received_instruction_for_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the system instruction during prompt upload."""
    if not update.message or not update.message.text or not update.effective_user:
        return prompt_manager.UPLOAD_PRIVATE_INSTRUCTION  # Stay in current state or handle error

    user_id = str(update.effective_user.id)
    instruction = update.message.text
    if context.user_data is None: context.user_data = {}

    log.debug(f"User {user_id} provided instruction for upload: '{instruction[:50]}...'")
    response_text = await prompt_manager.received_private_instruction_for_upload(user_id, instruction,
                                                                                 context.user_data)
    await update.message.reply_text(response_text)

    # Check if the instruction was accepted and we should move to the next state
    if 'private_instruction_to_upload' in context.user_data:
        return prompt_manager.UPLOAD_PRIVATE_NAME
    else:  # Instruction might have been empty or invalid, stay in current state
        return prompt_manager.UPLOAD_PRIVATE_INSTRUCTION


async def received_name_for_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the prompt name during prompt upload and creates the prompt."""
    if not update.message or not update.message.text or not update.effective_user:
        return ConversationHandler.END  # Or handle error appropriately

    user_id = str(update.effective_user.id)
    name = update.message.text
    if context.user_data is None: context.user_data = {}

    log.debug(f"User {user_id} provided name for upload: '{name}'")
    response_text = await prompt_manager.received_private_prompt_name_and_create(user_id, name, context.user_data)
    await update.message.reply_text(response_text)
    return ConversationHandler.END  # End conversation after attempting to create


async def received_new_instruction_for_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the new system instruction during prompt edit."""
    if not update.message or not update.message.text or not update.effective_user:
        log.error("Edit handler: Update, message, text, or user missing.")
        # Optionally, send a message to the user if possible
        if update.message:
            await update.message.reply_text("发生错误，无法处理您的输入。请重试或使用 /cancel。")
        return ConversationHandler.END  # End conversation on error

    user_id = str(update.effective_user.id)
    new_instruction = update.message.text
    if context.user_data is None:
        log.warning(f"User {user_id} - Edit handler: context.user_data is None. Initializing.")
        context.user_data = {}  # Should have been initialized by start_edit_private_prompt_flow

    log.info(
        f"User {user_id} - In received_new_instruction_for_edit_handler with instruction: '{new_instruction[:50]}...'")

    # This function from prompt_manager.py will attempt to update the SQL database
    response_text = await prompt_manager.received_new_instruction_for_edit(user_id, new_instruction, context.user_data)

    await update.message.reply_text(response_text)  # This is your "update finish" message
    return ConversationHandler.END  # End conversation after attempting to edit


async def main_async():  # Renamed to avoid conflict if you run main() at the end
    log.info("Starting bot application...")

    if not TELEGRAM_BOT_TOKEN:
        log.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    ensure_data_directory()
    init_db()
    log.info("Database initialized.")

    initialize_system_prompts()
    log.info("System prompts initialized.")

    gemini_service = GeminiService()
    log.info("GeminiService initialized.")

    # defaults = Defaults(parse_mode=ParseMode.MARKDOWN)

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        # .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    application.bot_data["gemini_service"] = gemini_service
    log.info("Telegram Application built and GeminiService stored in bot_data.")

    # --- Define ConversationHandlers ---
    # Assumes cancel_command_handler is in command_handlers module
    # and upload_prompt_command_handler is also in command_handlers
    upload_prompt_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload_prompt", command_handlers.upload_prompt_command_handler),
            # CallbackQueryHandler for create button is handled by private_prompts_callback_handler returning UPLOAD_PRIVATE_INSTRUCTION
        ],
        states={
            prompt_manager.UPLOAD_PRIVATE_INSTRUCTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                               received_instruction_for_upload_handler)
            ],
            prompt_manager.UPLOAD_PRIVATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                               received_name_for_upload_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", command_handlers.cancel_command_handler)],
        # If the callback handler is intended to be an entry point, map_to_state can be useful
        # or ensure it's part of application.add_handler before this ConversationHandler
        # and that the state it returns is correctly picked up.
        # For button-triggered conversations, the callback handler returning a state
        # effectively acts as an entry point if the ConversationHandler is already registered.
    )

    edit_prompt_conv_handler = ConversationHandler(
        entry_points=[
            # IMPORTANT: Entry for edit is when private_prompts_callback_handler returns
            # the EDIT_PRIVATE_INSTRUCTION state. No explicit command entry point here
            # is typically needed if the callback handler correctly returns the state.
        ],
        states={
            prompt_manager.EDIT_PRIVATE_INSTRUCTION: [  # This state is returned by callbacks.py
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,  # Catches user's text message
                    received_new_instruction_for_edit_handler  # Calls the function defined above
                )
            ]
            # Add other states here if your edit process had more steps
        },
        fallbacks=[CommandHandler("cancel", command_handlers.cancel_command_handler)],
        # per_user=True, per_chat=True are defaults and usually correct for this.
    )

    # --- Register Handlers ---
    # IMPORTANT: ConversationHandlers should typically be added before more general message handlers.
    application.add_handler(upload_prompt_conv_handler)
    application.add_handler(edit_prompt_conv_handler)

    # Basic command handlers
    application.add_handler(CommandHandler("start", base_handlers.start_command_handler))
    application.add_handler(CommandHandler("help", base_handlers.help_command_handler))
    application.add_handler(
        CommandHandler("cancel", command_handlers.cancel_command_handler))  # Ensure /cancel is standalone too

    # Prompt management commands
    application.add_handler(CommandHandler("my_prompts", command_handlers.my_prompts_command_handler))
    application.add_handler(CommandHandler("set_prompt", command_handlers.set_prompt_command_handler))
    # upload_prompt is an entry to a ConversationHandler, already added above.

    # Callback Query Handler for /my_prompts buttons
    # This handler (private_prompts_callback_handler) can return states
    # that will be picked up by the ConversationHandlers defined above.
    application.add_handler(CallbackQueryHandler(
        callback_handlers.private_prompts_callback_handler,
        pattern="^pr_"
    ))

    # General Private Message Handler (should be one of the last for private chats)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        base_handlers.private_message_handler
    ))

    # Error Handler
    application.add_error_handler(base_handlers.error_handler)

    log.info("All bot handlers registered.")
    log.info("Bot is starting to poll for updates...")
    try:
        await application.initialize()
        await application.updater.start_polling()  # type: ignore
        await application.start()
        log.info("Bot is running.")
        while True:
            await asyncio.sleep(3600)
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
    asyncio.run(main_async())  # Run the renamed async main function