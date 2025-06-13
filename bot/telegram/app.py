# bot/telegram/app.py
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Import our settings and logger
from bot.core.config import settings
from bot.core.logging import logger

# Import our database initializer and session factory
from bot.database import SessionLocal, init_db

# Import our custom services
from bot.services.gemini_service import GeminiService
from bot.services.prompt_service import PromptService
from bot.services.chat_service import ChatService

# Import our handler modules
from bot.telegram.handlers import commands, messages, callbacks, conversations



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
    """
    Builds the application and runs the bot.
    """
    logger.info("Building and configuring the bot application...")

    # Create the Application instance
    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)  # Register our setup function
        .build()
    )

    # --- Register all handlers ---

    # The ConversationHandler for adding prompts must be added before other handlers
    # that might handle the same updates (like generic message handlers).
    application.add_handler(conversations.add_prompt_conv_handler)

    # Command Handlers
    application.add_handler(CommandHandler("start", commands.start))
    application.add_handler(CommandHandler("help", commands.help_command))
    application.add_handler(CommandHandler("clear", commands.clear_command))
    application.add_handler(CommandHandler("my_prompts", commands.my_prompts_command))

    # Message Handler (for general text messages)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages.handle_message))

    # Callback Query Handler (for button clicks)
    application.add_handler(CallbackQueryHandler(callbacks.handle_callback_query))

    logger.info("All handlers registered.")

    # Start the bot
    logger.info("Starting bot polling...")
    application.run_polling()
