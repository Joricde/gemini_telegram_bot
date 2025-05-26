# gemini-telegram-bot/main.py

import asyncio

from telegram.constants import ParseMode
# ... other imports ...
from telegram.ext import Application, CommandHandler, MessageHandler, filters, Defaults, ConversationHandler, \
    CallbackQueryHandler  # Ensure CallbackQueryHandler is here

# ... (rest of the imports and initial setup code from your previous main.py) ...
from bot import (
    TELEGRAM_BOT_TOKEN,
    APP_CONFIG,
    PROMPTS_CONFIG,
    PROJECT_ROOT,
    GEMINI_SETTINGS,
    DEFAULT_BOT_BEHAVIOR,
    LOGGING_CONFIG
)
from bot.utils import log
from bot.database import engine, init_db, SessionLocal
from bot.database import models as db_models
from bot.database.crud import create_prompt, get_prompt_by_name
from bot.gemini_service import GeminiService
from bot.telegram_adapter import handlers  # Main handlers module
from bot.telegram_adapter.handlers import upload_prompt_conversation_handler  # Specific import for clarity


def ensure_data_directory():
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Created data directory: {data_dir}")


def initialize_system_prompts():
    db = SessionLocal()
    try:
        log.info("Initializing system prompts from config into database...")
        default_gen_params = GEMINI_SETTINGS.get("default_generation_parameters", {})

        for key, prompt_data in PROMPTS_CONFIG.items():
            prompt_name = prompt_data.get("name", key)
            existing_prompt = get_prompt_by_name(db, name=prompt_name)
            if not existing_prompt:
                created = create_prompt(
                    db=db,
                    name=prompt_name,
                    description=prompt_data.get("description"),
                    system_instruction=prompt_data.get("system_instruction", ""),
                    temperature=prompt_data.get("temperature", default_gen_params.get("temperature")),
                    top_p=prompt_data.get("top_p", default_gen_params.get("top_p")),
                    top_k=prompt_data.get("top_k", default_gen_params.get("top_k")),
                    max_output_tokens=prompt_data.get("max_output_tokens", default_gen_params.get("max_output_tokens")),
                    base_model_override=prompt_data.get("base_model_override"),
                    is_system_default=True
                )
                if created:
                    log.info(f"Added system prompt to DB: '{prompt_name}' (ID: {created.id})")
                else:
                    log.error(f"Failed to add system prompt to DB: '{prompt_name}'")
    except Exception as e:
        log.error(f"Error initializing system prompts: {e}", exc_info=True)
    finally:
        db.close()


async def post_init(application: Application):
    log.info("Running post_init hook...")
    await application.bot.set_my_commands([
        ("start", "🚀 开始/帮助"),
        ("help", "ℹ️ 显示帮助信息"),
        ("my_prompts", "📚 查看并选择角色"),
        ("upload_prompt", "✍️ 上传新的角色定义"),
        ("cancel", "❌ 取消当前操作"),
    ])
    log.info("Bot commands set.")


async def main():
    log.info("Starting bot application...")

    if not TELEGRAM_BOT_TOKEN:
        log.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    ensure_data_directory()
    init_db()
    log.info("Database initialized (tables created if not exist).")
    initialize_system_prompts()

    gemini_service = GeminiService()
    log.info("GeminiService initialized.")

    defaults = Defaults(parse_mode=ParseMode.MARKDOWN)

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    application.bot_data["gemini_service"] = gemini_service
    log.info("Telegram Application built.")

    application.add_handler(CommandHandler("start", handlers.start_command_handler))
    application.add_handler(CommandHandler("help", handlers.help_command_handler))
    application.add_handler(handlers.upload_prompt_conversation_handler)
    application.add_handler(CommandHandler("my_prompts", handlers.my_prompts_command_handler))

    # Updated CallbackQueryHandler pattern to catch both types of callbacks
    application.add_handler(CallbackQueryHandler(handlers.handle_prompt_selection_callback,
                                                 pattern="^(set_prompt_id:|prompt_page:|noop_page_indicator)"))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handlers.private_message_handler
    ))
    application.add_error_handler(handlers.error_handler)
    log.info("Bot handlers registered.")

    log.info("Bot is starting to poll for updates...")
    try:
        await application.initialize()
        await application.updater.start_polling()  # type: ignore
        await application.start()
        log.info("Bot is running.")
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot shutting down...")
    finally:
        if application.updater and application.updater.running:  # type: ignore
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        log.info("Bot has been shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.critical(f"Application failed to run: {e}", exc_info=True)