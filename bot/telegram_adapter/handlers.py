# gemini-telegram-bot/bot/telegram_adapter/handlers.py

import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,  # Add CommandHandler to imports
    MessageHandler,  # Add MessageHandler to imports
    filters  # Add filters to imports
)
from telegram.constants import ChatAction

from bot.utils import log
from bot.database import SessionLocal
from bot.database.crud import get_or_create_user
from bot.message_processing.private_chat import handle_private_message
# Import prompt manager functions and states
from bot.message_processing.prompt_manager import (
    start_upload_prompt,
    received_system_instruction,
    received_prompt_name_and_create,
    cancel_upload_prompt,
    list_my_prompts,
    set_active_prompt,
    NAME, SYSTEM_INSTRUCTION  # States for ConversationHandler
)
from bot.gemini_service import GeminiService


async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    if not user:
        log.warning("Could not get effective_user in start_command_handler")
        return

    # Ensure user exists in DB when they /start
    # Running synchronous DB operation in a separate thread
    def sync_db_ops():
        db = SessionLocal()
        try:
            db_user = get_or_create_user(
                db,
                user_id=str(user.id),
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            return db_user.first_name or db_user.username
        finally:
            db.close()

    user_display_name = await asyncio.to_thread(sync_db_ops)
    log.info(f"User {user.id} ({user.username}) started bot with /start")

    welcome_message = (
        f"你好，{user_display_name or user.mention_markdown()} \\! 👋\n\n"
        f"我是一个由 Gemini 驱动的智能聊天机器人。你可以直接向我发送消息开始对话。\n\n"
        f"**常用命令**:\n"
        f"`/start` 或 `/help` \\- 显示此帮助信息\n"
        f"`/my_prompts` \\- 查看和管理你的可用角色\n"
        f"`/set_prompt <角色名>` \\- 切换当前对话角色\n"
        f"`/upload_prompt` \\- 创建一个新的自定义角色\n"
        # Add more commands as you implement them, e.g.:
        # ("/mode", "🔧 (群管理员) 设置群聊模式"),
    )

    await update.message.reply_markdown(
        text=welcome_message,
    )


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /start command."""
    await start_command_handler(update, context)


# --- Prompt Management Command Handlers ---

async def upload_prompt_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the prompt upload conversation."""
    if not update.effective_user:
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} initiated /upload_prompt.")

    # Ensure context.user_data is initialized
    if not hasattr(context, 'user_data') or context.user_data is None:
        context.user_data = {}

    response_text = await start_upload_prompt(user_id)
    await update.message.reply_text(response_text, parse_mode='Markdown')
    return SYSTEM_INSTRUCTION  # Next state: waiting for system instruction


async def system_instruction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the system instruction."""
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END  # Or some error state

    user_id = str(update.effective_user.id)
    instruction = update.message.text
    log.debug(f"User {user_id} provided system instruction for new prompt.")

    # Ensure context.user_data is initialized
    if not hasattr(context, 'user_data') or context.user_data is None:
        context.user_data = {}  # Should have been set by start

    response_text = await received_system_instruction(user_id, instruction, context.user_data)
    await update.message.reply_text(response_text)
    return NAME  # Next state: waiting for prompt name


async def prompt_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the prompt name and creates the prompt."""
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    name = update.message.text.strip()
    log.debug(f"User {user_id} provided name '{name}' for new prompt.")

    # Ensure context.user_data is initialized
    if not hasattr(context, 'user_data') or context.user_data is None:
        # This should not happen if conversation flows correctly
        await update.message.reply_text("发生内部错误，请重新开始 /upload_prompt。")
        return ConversationHandler.END

    response_text = await received_prompt_name_and_create(user_id, name, context.user_data)
    await update.message.reply_text(response_text)
    return ConversationHandler.END  # End conversation


async def cancel_prompt_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the prompt upload conversation."""
    if not update.effective_user:
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    # Ensure context.user_data is initialized
    if not hasattr(context, 'user_data') or context.user_data is None:
        context.user_data = {}

    response_text = await cancel_upload_prompt(user_id, context.user_data)
    await update.message.reply_text(response_text)
    return ConversationHandler.END


async def my_prompts_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /my_prompts command."""
    if not update.effective_user:
        return
    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} requested /my_prompts.")
    response_text = await list_my_prompts(user_id)
    await update.message.reply_text(response_text)


async def set_prompt_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /set_prompt command."""
    if not update.effective_user or not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("请提供角色名称或ID。用法: `/set_prompt <角色名称或ID>`")
        return

    prompt_identifier = " ".join(context.args)  # Allow names with spaces
    log.info(f"User {user_id} requested /set_prompt for '{prompt_identifier}'.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    response_text = await set_active_prompt(user_id, prompt_identifier)
    await update.message.reply_text(response_text, parse_mode='Markdown')


# --- Message Handlers (Private Chat) ---
async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles private text messages by invoking the private_chat business logic."""
    message = update.message
    user = update.effective_user

    if not message or not message.text or not user:
        log.debug("Ignoring empty message or message without user.")
        return

    log.info(f"Private message from {user.id} ({user.username}) to process: '{message.text[:50]}...'")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    gemini_service_instance = context.bot_data.get("gemini_service")
    if not isinstance(gemini_service_instance, GeminiService):
        log.error("GeminiService not found or not of correct type in bot_data.")
        await message.reply_text("抱歉，AI服务当前不可用，请稍后再试。")
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
        await message.reply_text(response_text, parse_mode='Markdown')  # Consider Markdown for Gemini output
    else:
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


# --- ConversationHandler for /upload_prompt ---
upload_prompt_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("upload_prompt", upload_prompt_command_handler)],
    states={
        SYSTEM_INSTRUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, system_instruction_handler)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_name_handler)],
    },
    fallbacks=[CommandHandler("cancel", cancel_prompt_upload_handler)],
    # Optionally, add conversation timeout
    # conversation_timeout=300 # 5 minutes
)