# gemini-telegram-bot/main.py

import asyncio
import os
from pathlib import Path

# 确保 bot 包能被正确导入 (如果从根目录运行 main.py)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from telegram.ext import Application, CommandHandler, MessageHandler, filters, Defaults
from telegram.constants import ParseMode

from bot import (
    TELEGRAM_BOT_TOKEN,
    APP_CONFIG,
    PROMPTS_CONFIG,
    PROJECT_ROOT,
    # 从 bot.__init__ 导入已经实例化的服务或配置
    GEMINI_SETTINGS, # 示例，根据你在 bot.__init__ 中暴露的为准
    DEFAULT_BOT_BEHAVIOR,
    LOGGING_CONFIG
)
from bot.utils import log # 导入我们配置好的 logger
from bot.database import engine, init_db, SessionLocal
from bot.database import models as db_models # 确保所有模型被 SQLAlchemy 知道
from bot.database.crud import create_prompt, get_prompt_by_name # 用于初始化 prompts
from bot.gemini_service import GeminiService
from bot.telegram_adapter import handlers # 导入我们的处理器

# --- Application Setup Functions ---
def ensure_data_directory():
    """Ensures the data directory for SQLite exists."""
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Created data directory: {data_dir}")

def initialize_system_prompts():
    """Loads prompts from prompts.yml into the database if they don't exist."""
    db = SessionLocal()
    try:
        log.info("Initializing system prompts from config into database...")
        default_gen_params = GEMINI_SETTINGS.get("default_generation_parameters", {})
        # default_base_model = GEMINI_SETTINGS.get("default_base_model", "gemini-1.5-flash") # 已在GeminiService处理

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
            # else:
            # log.debug(f"System prompt '{prompt_name}' (ID: {existing_prompt.id}) already exists in DB.")
    except Exception as e:
        log.error(f"Error initializing system prompts: {e}", exc_info=True)
    finally:
        db.close()

async def post_init(application: Application):
    """
    Hook to run after Application has been initialized but before it starts.
    Useful for setting bot commands, etc.
    """
    log.info("Running post_init hook...")
    await application.bot.set_my_commands([
        ("start", "🚀 开始与机器人对话 / 显示帮助"),
        # Add more commands as you implement them, e.g.:
        # ("set_prompt", "🎨 设置当前对话的角色"),
        # ("my_prompts", "📚 查看我的可用角色"),
        # ("upload_prompt", "✍️ 上传新的角色定义"),
        # ("mode", "🔧 (群管理员) 设置群聊模式"),
    ])
    log.info("Bot commands set.")


async def main():
    """Main function to setup and run the bot."""
    log.info("Starting bot application...")

    if not TELEGRAM_BOT_TOKEN:
        log.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    # 1. Ensure data directory for SQLite
    ensure_data_directory()

    # 2. Initialize Database (create tables)
    # db_models.Base.metadata.create_all(bind=engine) # Ensure models are loaded
    init_db() # Calls Base.metadata.create_all(bind=engine)
    log.info("Database initialized (tables created if not exist).")

    # 3. Load system prompts from YML into DB
    initialize_system_prompts()

    # 4. Initialize services
    gemini_service = GeminiService()
    log.info("GeminiService initialized.")

    # 5. Setup Telegram Bot Application
    # Set default parse mode for messages
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN) # Or HTML, if you prefer

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .defaults(defaults)
        .post_init(post_init) # Hook after initialization
        .build()
    )

    # Store service instances in bot_data for access in handlers
    # This is a common way to share state/services with handlers in python-telegram-bot
    application.bot_data["gemini_service"] = gemini_service
    # application.bot_data["db_session_factory"] = SessionLocal # Handlers can create sessions

    log.info("Telegram Application built.")

    # 6. Register Handlers (from bot.telegram_adapter.handlers)
    # Basic handlers for now, will be expanded in Stage 2 for private chat
    application.add_handler(CommandHandler("start", handlers.start_command_handler))
    application.add_handler(CommandHandler("help", handlers.help_command_handler)) # Alias /help to /start for now

    # A simple echo handler for private messages (will be replaced by actual chat logic)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handlers.private_message_handler
    ))

    # Error handler
    application.add_error_handler(handlers.error_handler)
    log.info("Bot handlers registered.")

    # 7. Run the Bot
    log.info("Bot is starting to poll for updates...")
    try:
        await application.initialize() # Initialize handlers, etc.
        await application.updater.start_polling() # Start polling (non-blocking)
        await application.start() # Also non-blocking, keeps the application alive
        log.info("Bot is running.")
        # Keep the script running until interrupted (e.g., Ctrl+C)
        while True:
            await asyncio.sleep(3600) # Sleep for a long time
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot shutting down...")
    finally:
        if application.updater and application.updater.running: # type: ignore
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        log.info("Bot has been shut down.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        log.critical(f"Application failed to run: {e}", exc_info=True)