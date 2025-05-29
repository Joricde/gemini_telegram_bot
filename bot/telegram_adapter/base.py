# gemini-telegram-bot/bot/telegram_adapter/base.py

from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.utils import log
from bot.database import SessionLocal
from bot.database.crud import get_or_create_user
from bot.message_processing.private_chat import handle_private_message
from bot.gemini_service import GeminiService


async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and basic instructions when the /start command is issued."""
    user = update.effective_user
    if not user:
        log.warning("Could not get effective_user in start_command_handler")
        return

    db = SessionLocal()
    try:
        db_user = get_or_create_user(
            db,
            user_id=str(user.id),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        user_display_name = db_user.first_name or db_user.username or "用户"
    finally:
        db.close()

    log.info(f"User {user.id} ({user.username}) started bot with /start")

    welcome_message = (
        f"你好，{user_display_name}! 👋\n\n"
        f"我是一个由 Gemini 驱动的智能聊天机器人。\n"
        f"你可以直接向我发送消息开始对话。\n\n"
        f"**常用命令**:\n"
        f"`/start` 或 `/help` - 显示此帮助信息\n"
        f"`/my_prompts` - 查看和选择你的私人角色\n"
        f"`/upload_prompt` - 创建一个新的自定义私人角色\n"
        f"`/cancel` - 在创建或编辑角色等操作中途取消\n"
        # More commands will be added to the help message as they are implemented
    )
    if update.message:
        await update.message.reply_text(text=welcome_message, parse_mode=ParseMode.MARKDOWN)


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends help message; currently aliases to start_command_handler."""
    await start_command_handler(update, context)


async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles direct private text messages from users that are not part of an ongoing conversation.
    """
    message = update.message
    user = update.effective_user

    if not message or not message.text or not user:
        log.debug("Ignoring empty message, non-text message, or message without user in private_message_handler.")
        return

    if message.chat.type != "private":
        log.debug(f"Ignoring message from non-private chat ({message.chat.type}) in private_message_handler.")
        return

    # Check if a conversation is active for this user (PTB does this implicitly if this handler is added after ConvHandlers)
    # If this handler is intended to catch messages ONLY when no conversation is active,
    # its placement in application.add_handler matters, or more explicit checks are needed.
    # For now, assume it's for general private messages.

    log.info(f"General private message from {user.id} ({user.username}): '{message.text[:50]}...'")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    gemini_service_instance = context.bot_data.get("gemini_service")
    if not isinstance(gemini_service_instance, GeminiService):
        log.error("GeminiService not found or not of correct type in bot_data.")
        if message: await message.reply_text("抱歉，AI服务当前不可用，请稍后再试。")
        return

    try:
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
        try:
            if message: await message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            log.error(f"Error sending reply to user {user.id}: {e}", exc_info=True)
            try:
                if message: await message.reply_text(response_text)
            except Exception as e_plain:
                log.error(f"Error sending reply as plain text to user {user.id}: {e_plain}", exc_info=True)
    elif message:  # Only reply if message object exists
        log.warning(f"handle_private_message returned None or empty string for user {user.id}. Sending generic error.")
        await message.reply_text("抱歉，我无法处理您的请求或AI未能生成有效回复。")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates and send a user-friendly message."""
    log.error(msg="Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="抱歉，处理您的请求时发生了一个内部错误。我们已记录此问题。"
            )
        except Exception as e:
            log.error(f"Failed to send error message to user after an error: {e}")

