# bot/telegram/handlers/commands.py
from telegram import Update
from telegram.ext import ContextTypes

from bot.database import crud
from bot.telegram import keyboards
from bot.services.prompt_service import PromptService
from bot.core.logging import logger


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /start command.
    Greets the user, creates them in the DB, and shows the main menu.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"/start command received from user {user.id} in chat {chat_id}")

    # Retrieve the db session from context
    db = context.bot_data["db_session"]

    # Create the user in the database if they don't exist
    crud.get_or_create_user(db=db, user_data=user)

    # Prepare the welcome message and keyboard
    welcome_text = (
        f"Hi {user.first_name}! I'm your personal Gemini assistant. "
        "Let's start chatting, or you can use the menu below to manage our conversation."
    )
    keyboard = keyboards.create_start_menu_keyboard()

    await update.message.reply_text(welcome_text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /help command.
    Displays a helpful message with a list of commands.
    """
    user = update.effective_user
    logger.info(f"/help command received from user {user.id}")

    help_text = (
        "Here's how I can help you:\n\n"
        "• Just send me a message and I'll respond!\n"
        "• /start - Shows the main menu.\n"
        "• /my_prompts - View and manage your custom personas for me.\n"
        "• /clear - Clears our recent conversation history, giving us a fresh start.\n"
        "• /help - Shows this help message."
    )

    await update.message.reply_text(help_text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /clear command.
    Resets the user's chat session history.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"/clear command received from user {user.id} in chat {chat_id}")

    db = context.bot_data["db_session"]
    crud.reset_session(db=db, chat_id=chat_id)

    await update.message.reply_text("✨ Our conversation history has been cleared.")


async def my_prompts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /my_prompts command.
    Displays a list of all available prompts with selection buttons.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    logger.info(f"/my_prompts command from user {user.id} in chat {chat_id}")

    prompt_service: PromptService = context.bot_data["prompt_service"]
    db = context.bot_data["db_session"]

    # Get all available prompts (from YAML and DB)
    all_prompts = prompt_service.get_available_prompts()

    # Get the active key for the current chat session
    session = crud.get_or_create_session(db=db, chat_id=chat_id)
    active_key = session.active_prompt_key

    if not all_prompts:
        await update.message.reply_text(
            "No prompts are available. You can add a new shared one via the menu."
        )
        return

    # Pass the full list and the active key to the keyboard builder
    keyboard = keyboards.create_prompt_list_keyboard(prompts=all_prompts, active_key=active_key)
    await update.message.reply_text(
        "Here are the available personas. Click one to make it active for this chat.",
        reply_markup=keyboard
    )
