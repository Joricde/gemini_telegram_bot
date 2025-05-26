# gemini-telegram-bot/bot/telegram_adapter/handlers.py

import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from bot.utils import log
from bot.database import SessionLocal
from bot.database.crud import get_or_create_user
from bot.message_processing.private_chat import handle_private_message  # MODIFIED
from bot.gemini_service import GeminiService  # To get type hint for context.bot_data


# ... (start_command_handler, help_command_handler remain the same) ...
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    if not user:
        log.warning("Could not get effective_user in start_command_handler")
        return

    log.info(f"User {user.id} ({user.username}) started bot with /start")

    async def sync_db_get_or_create_user():
        db = SessionLocal()
        try:
            db_user = await asyncio.to_thread(
                get_or_create_user,
                db,
                user_id=str(user.id),
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            return db_user.first_name or db_user.username
        finally:
            db.close()

    user_display_name = await asyncio.to_thread(sync_db_get_or_create_user)

    welcome_message = (
        f"你好，{user_display_name or user.mention_markdown_v2()} \\! 👋\n\n"
        f"我是一个由 Gemini 驱动的智能聊天机器人。你可以直接向我发送消息开始对话。\n\n"
        f"可用的命令:\n"
        f"`/start` 或 `/help` \\- 显示此帮助信息\n"
    )

    await update.message.reply_markdown_v2(
        text=welcome_message,
    )


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /start command."""
    await start_command_handler(update, context)


# --- Message Handlers ---
async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # MODIFIED
    """Handles private text messages by invoking the private_chat business logic."""
    message = update.message
    user = update.effective_user

    if not message or not message.text or not user:
        log.debug("Ignoring empty message or message without user.")
        return

    log.info(f"Private message from {user.id} ({user.username}) to process: '{message.text[:50]}...'")  # Log a snippet

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    gemini_service_instance = context.bot_data.get("gemini_service")
    if not isinstance(gemini_service_instance, GeminiService):  # Check if it's the correct type
        log.error("GeminiService not found or not of correct type in bot_data.")
        await message.reply_text("抱歉，AI服务当前不可用，请稍后再试。")
        return

    # Call the business logic function, running it in a separate thread
    # because handle_private_message itself contains synchronous DB operations.
    # The Gemini call within handle_private_message is async, so handle_private_message itself is async.
    # No, handle_private_message contains sync db calls, so it should be run in a thread if called from async.
    # Or, the DB calls within handle_private_message should be made async (e.g. using asyncio.to_thread for each).
    # For simplicity now, let's assume handle_private_message's DB calls are quick or we make it fully async.
    #
    # Let's make handle_private_message fully async by using asyncio.to_thread for its DB parts.
    # If handle_private_message is defined as `async def`, we can directly await it.

    try:
        # Pass user details and message text to the handler function
        response_text = await handle_private_message(
            user_id=str(user.id),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            message_text=message.text,
            gemini_service=gemini_service_instance
        )
    except Exception as e:
        log.error(f"Unhandled exception in private_message_handler calling handle_private_message: {e}", exc_info=True)
        response_text = "处理您的消息时发生了非常意外的错误。"

    if response_text:
        # log.info(response_text)
        await message.reply_text(response_text)
    else:
        # This case should ideally be handled within handle_private_message to return a user-friendly error.
        log.warning(f"handle_private_message returned None for user {user.id}")
        await message.reply_text("抱歉，我无法处理您的请求。")


# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    log.error(msg="Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="抱歉，处理您的请求时发生了一个内部错误。我已经记录了这个问题。"
            )
        except Exception as e:
            log.error(f"Failed to send error message to user: {e}")