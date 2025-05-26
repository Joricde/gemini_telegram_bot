# gemini-telegram-bot/bot/telegram_adapter/handlers.py

import asyncio
import math  # For math.ceil for total_pages calculation
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from telegram.constants import ChatAction, ParseMode

from bot.utils import log
from bot.database import SessionLocal
from bot.database import models as db_models  # For type hinting
from bot.database.crud import (
    get_or_create_user,
    get_prompts_by_user,
    get_system_default_prompts,
    get_active_chat_session_state
)
from bot.message_processing.private_chat import handle_private_message
from bot.message_processing.prompt_manager import (
    start_upload_prompt,
    received_system_instruction,
    received_prompt_name_and_create,
    cancel_upload_prompt,
    set_active_prompt,
    NAME, SYSTEM_INSTRUCTION
)
from bot.gemini_service import GeminiService

# --- Constants for Pagination ---
PROMPTS_PER_PAGE = 15  # 5 rows * 3 columns
PROMPT_BUTTON_COLS = 3


# --- Helper Function to Generate Prompt Keyboard ---
async def _generate_prompt_keyboard_and_text(user_id: str, page: int = 0) -> tuple[Optional[InlineKeyboardMarkup], str]:
    """
    Generates the InlineKeyboardMarkup and message text for a given page of prompts.
    """
    db = SessionLocal()
    try:
        user_prompts = get_prompts_by_user(db, user_id=user_id)
        system_prompts = get_system_default_prompts(db)
        active_session = get_active_chat_session_state(db, telegram_chat_id=user_id, telegram_user_id=user_id)
        active_prompt_id_in_session = active_session.active_prompt_id if active_session else None
    finally:
        db.close()

    all_prompts: list[db_models.Prompt] = []
    # Add headers/sections if desired, or just combine lists
    # For simplicity, we'll combine them and note their origin if needed by button text later
    # Or, we can process them in sections for the keyboard

    # Create a list of tuples: (prompt_object, type_string)
    categorized_prompts = []
    if user_prompts:
        for p in user_prompts:
            categorized_prompts.append((p, "user"))
    if system_prompts:
        for p in system_prompts:
            categorized_prompts.append((p, "system"))

    if not categorized_prompts:
        return None, "目前没有可用的角色。使用 /upload_prompt 创建一个吧！"

    total_prompts = len(categorized_prompts)
    total_pages = math.ceil(total_prompts / PROMPTS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))  # Ensure page is within valid range

    start_index = page * PROMPTS_PER_PAGE
    end_index = start_index + PROMPTS_PER_PAGE
    prompts_to_display = categorized_prompts[start_index:end_index]

    keyboard: list[list[InlineKeyboardButton]] = []

    # Add user prompts section if any are on this page
    current_row: list[InlineKeyboardButton] = []
    for prompt, p_type in prompts_to_display:
        is_active_char = "🔹" if prompt.id == active_prompt_id_in_session else "▪️"
        button_text = f"{is_active_char} {prompt.name}"
        # Truncate button text if too long for Telegram buttons (approx 64 bytes for callback_data, text similar)
        if len(button_text.encode('utf-8')) > 50:  # Rough estimate
            button_text = button_text[:15] + "..."  # Adjust as needed

        current_row.append(InlineKeyboardButton(button_text, callback_data=f"set_prompt_id:{prompt.id}"))
        if len(current_row) == PROMPT_BUTTON_COLS:
            keyboard.append(current_row)
            current_row = []
    if current_row:  # Add any remaining buttons in the last row
        keyboard.append(current_row)

    # Navigation buttons
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"prompt_page:{page - 1}"))

    # Page indicator (can be made non-clickable if preferred)
    nav_row.append(InlineKeyboardButton(f"第 {page + 1}/{total_pages} 页", callback_data="noop_page_indicator"))

    if end_index < total_prompts:
        nav_row.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"prompt_page:{page + 1}"))

    if nav_row:
        keyboard.append(nav_row)

    message_text = f"请选择一个角色 (第 {page + 1}/{total_pages} 页):"
    return InlineKeyboardMarkup(keyboard), message_text


# --- Command Handlers ---
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # ... (rest of start_command_handler as before)
    if not user:
        log.warning("Could not get effective_user in start_command_handler")
        return

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
            return user.first_name or user.username
        finally:
            db.close()

    user_display_name = await asyncio.to_thread(sync_db_ops)
    log.info(f"User {user.id} ({user.username}) started bot with /start")

    welcome_message = (
        f"你好，{user_display_name or '用户'}! 👋\n\n"
        f"我是一个由 Gemini 驱动的智能聊天机器人。\n"
        f"你可以直接向我发送消息开始对话。\n\n"
        f"**常用命令**:\n"
        f"`/start` 或 `/help` - 显示此帮助信息\n"
        f"`/my_prompts` - 查看和选择你的可用角色\n"
        f"`/upload_prompt` - 创建一个新的自定义角色\n"
    )
    await update.message.reply_text(text=welcome_message, parse_mode=ParseMode.MARKDOWN)


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_command_handler(update, context)


async def my_prompts_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /my_prompts command by displaying the first page of prompts."""
    if not update.effective_user:
        return
    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} requested /my_prompts (initial page).")

    reply_markup, message_text = await _generate_prompt_keyboard_and_text(user_id, page=0)

    if reply_markup:
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(message_text)  # e.g., "No prompts available"


# --- Callback Query Handler ---
async def handle_prompt_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles prompt selection or page navigation from inline keyboard."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if not user:
        log.warning("No effective_user in prompt selection callback.")
        await query.edit_message_text(text="无法识别用户，请重试。")
        return
    user_id = str(user.id)

    callback_data = query.data

    if callback_data and callback_data.startswith("set_prompt_id:"):
        try:
            prompt_id_str = callback_data.split(":", 1)[1]
            if not prompt_id_str.isdigit():
                raise ValueError("Prompt ID in callback_data is not a digit.")
            # prompt_id = int(prompt_id_str) # No longer needed as set_active_prompt takes string
        except (IndexError, ValueError) as e:
            log.error(f"Error parsing prompt_id from callback_data '{callback_data}': {e}")
            await query.edit_message_text(text="选择角色时数据错误，请重试。")
            return

        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        response_text = await set_active_prompt(user_id, prompt_id_str)  # Pass ID as string
        await query.edit_message_text(text=response_text, parse_mode=ParseMode.MARKDOWN)

    elif callback_data and callback_data.startswith("prompt_page:"):
        try:
            page_str = callback_data.split(":", 1)[1]
            if not page_str.isdigit():
                raise ValueError("Page number in callback_data is not a digit.")
            page = int(page_str)
        except (IndexError, ValueError) as e:
            log.error(f"Error parsing page number from callback_data '{callback_data}': {e}")
            await query.edit_message_text(text="翻页时数据错误，请重试。")
            return

        log.info(f"User {user_id} navigating to prompt page {page}.")
        reply_markup, message_text = await _generate_prompt_keyboard_and_text(user_id, page=page)
        if reply_markup:
            await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:  # Should not happen if pages are calculated correctly, but as a fallback
            await query.edit_message_text(text=message_text)

    elif callback_data == "noop_page_indicator":
        # Do nothing for the page indicator button if it's made clickable for some reason
        pass
    else:
        log.warning(f"Received unhandled callback_data: {callback_data} from user {user_id}")
        # Optionally, provide feedback to the user if it's an unexpected callback
        # await query.edit_message_text(text="未知操作。")


# --- Upload Prompt Conversation Handlers ---
# (upload_prompt_command_handler, system_instruction_handler, prompt_name_handler, cancel_prompt_upload_handler)
# ... remain unchanged from your previous version ...
async def upload_prompt_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END
    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} initiated /upload_prompt.")

    if not hasattr(context, 'user_data') or context.user_data is None:
        context.user_data = {}

    response_text = await start_upload_prompt(user_id)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
    return SYSTEM_INSTRUCTION


async def system_instruction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    instruction = update.message.text
    log.debug(f"User {user_id} provided system instruction for new prompt.")

    if not hasattr(context, 'user_data') or context.user_data is None:
        context.user_data = {}

    response_text = await received_system_instruction(user_id, instruction, context.user_data)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
    return NAME


async def prompt_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    name = update.message.text.strip()
    log.debug(f"User {user_id} provided name '{name}' for new prompt.")

    if not hasattr(context, 'user_data') or context.user_data is None:
        await update.message.reply_text("发生内部错误，请重新开始 /upload_prompt。")
        return ConversationHandler.END

    response_text = await received_prompt_name_and_create(user_id, name, context.user_data)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def cancel_prompt_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user:
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    if not hasattr(context, 'user_data') or context.user_data is None:
        context.user_data = {}

    response_text = await cancel_upload_prompt(user_id, context.user_data)
    await update.message.reply_text(response_text)
    return ConversationHandler.END


upload_prompt_conversation_handler = ConversationHandler(
    entry_points=[CommandHandler("upload_prompt", upload_prompt_command_handler)],
    states={
        SYSTEM_INSTRUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, system_instruction_handler)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_name_handler)],
    },
    fallbacks=[CommandHandler("cancel", cancel_prompt_upload_handler)],
)


# --- Private Message Handler ---
# ... (private_message_handler remains unchanged) ...
async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
    else:
        log.warning(f"handle_private_message returned None for user {user.id}")
        await message.reply_text("抱歉，我无法处理您的请求。")


# --- Error Handler ---
# ... (error_handler remains unchanged) ...
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error(msg="Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="抱歉，处理您的请求时发生了一个内部错误。我已经记录了这个问题。"
            )
        except Exception as e:
            log.error(f"Failed to send error message to user: {e}")