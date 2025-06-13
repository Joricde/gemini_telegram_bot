# bot/telegram/app.py
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters, ConversationHandler,
)

# Import our settings and logger
from bot.core.config import settings
from bot.core.logging import logger

from bot.database import SessionLocal, init_db

from bot.services.gemini_service import GeminiService
from bot.services.prompt_service import PromptService
from bot.services.chat_service import ChatService

from .handlers import commands, messages, callbacks
from .handlers.conversations import ( # <--- 2. 导入我们新的对话处理函数和状态
    add_prompt_start,
    received_prompt_text,
    cancel_conversation,
    AWAITING_PROMPT_TEXT
)



async def post_init(application: Application) -> None:
    """
    A function that runs after the Application is built but before polling starts.
    This is the perfect place to initialize our database and services.
    """
    logger.info("Running post-initialization setup...")

    # 1. Initialize the database (create tables)
    init_db()

    # 2. Create a single database session to be shared across all handlers for the bot's lifecycle
    db_session = SessionLocal()

    # 3. Initialize our services
    gemini_service = GeminiService()
    prompt_service = PromptService(db=db_session)
    chat_service = ChatService(db=db_session, gemini_service=gemini_service, prompt_service=prompt_service)

    # 4. Store the session and services in the bot_data dictionary.
    # This makes them accessible in any handler via context.bot_data.
    application.bot_data["db_session"] = db_session
    application.bot_data["gemini_service"] = gemini_service
    application.bot_data["prompt_service"] = prompt_service
    application.bot_data["chat_service"] = chat_service

    commands_to_set = [
        BotCommand("start", "Restart the bot and show the main menu"),
        BotCommand("my_prompts", "View and manage your personas"),
        BotCommand("clear", "Clear the current conversation history"),
        BotCommand("help", "Show help information"),
    ]
    await application.bot.set_my_commands(commands_to_set)

    logger.info("Services and database session initialized and stored in bot_data.")


def run() -> None:
    """Initializes and runs the Telegram bot."""
    logger.info("Building and configuring the bot application...")

    # Create the Application instance
    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)  # Register our setup function
        .build()
    )
    add_prompt_conv_handler = ConversationHandler(
        entry_points=[
            # 对话的入口是点击 "＋ Add New" 按钮
            CallbackQueryHandler(add_prompt_start, pattern="^add_new_prompt$")
        ],
        states={
            # 定义不同状态下应该由哪个函数处理
            AWAITING_PROMPT_TEXT: [
                # 当用户发送任何文本消息时（不包括命令），由 received_prompt_text 处理
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_prompt_text)
            ],
        },
        fallbacks=[
            # 定义后备/取消方案
            CommandHandler("cancel", cancel_conversation)
        ],
        # 可选：如果对话长时间没有响应，可以自动超时
        conversation_timeout=300  # 5分钟
    )

    # --- 4. 注册 Handlers 到 Application ---
    # 注意：ConversationHandler 应该在其他可能冲突的 handler 之前注册
    application.add_handler(add_prompt_conv_handler)

    # 注册其他常规 Handlers
    application.add_handler(CommandHandler("start", commands.start))
    application.add_handler(CommandHandler("my_prompts", commands.my_prompts_command))
    application.add_handler(CommandHandler("clear", commands.clear_command))
    application.add_handler(CommandHandler("help", commands.help_command))

    # CallbackQueryHandler 现在处理除 add_new_prompt 之外的所有回调
    application.add_handler(CallbackQueryHandler(callbacks.handle_callback_query))

    # MessageHandler 应该在最后，作为默认处理器
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages.handle_message))

    logger.info("All handlers registered.")

    # Start the bot
    logger.info("Starting bot polling...")
    application.run_polling()
