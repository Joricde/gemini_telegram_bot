# gemini-telegram-bot/bot/telegram_adapter/commands.py

import math
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.utils import log
from bot.database import SessionLocal
from bot.database import models as db_models  # For type hinting Prompt objects
from bot.database.models import PromptType
from bot.database.crud import (
    get_prompts_by_user_and_type,
    get_system_default_prompts,
    get_active_chat_session_state
)

# --- Constants for Callback Data (relevant to /my_prompts) ---
# These might be moved to a central constants file or __init__.py of telegram_adapter later
# if they are used by multiple files (e.g., callbacks.py will also use these).
# For now, defining them here for clarity of what this module handles.
CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE = "pr_page:"
CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT = "pr_select:"
CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT = "pr_edit:"
CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT = "pr_delete:"
CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT = "pr_create_new"
CALLBACK_NOOP_PAGE_INDICATOR = "pr_noop_page"

PROMPTS_PER_PAGE = 9  # 3 prompts per row, 3 rows.
PROMPT_BUTTON_COLS = 1  # Changing to 1 prompt per row for Select/Edit/Delete buttons side-by-side


# --- Helper Function to Generate Prompt Keyboard for /my_prompts ---
async def _generate_my_prompts_keyboard(
        user_id: str,
        page: int = 0
) -> tuple[Optional[InlineKeyboardMarkup], str]:
    """
    Generates the InlineKeyboardMarkup and message text for a given page of
    the user's private prompts and system default private prompts.
    """
    db = SessionLocal()
    try:
        user_private_prompts = get_prompts_by_user_and_type(db, user_id=user_id, prompt_type=PromptType.PRIVATE)
        system_private_prompts = get_system_default_prompts(db, prompt_type=PromptType.PRIVATE)

        active_session = get_active_chat_session_state(db, telegram_chat_id=user_id, telegram_user_id=user_id)
        active_prompt_id_in_session = active_session.active_prompt_id if active_session and active_session.active_prompt and active_session.active_prompt.prompt_type == PromptType.PRIVATE else None
    finally:
        db.close()

    categorized_prompts: list[tuple[db_models.Prompt, str, bool]] = []

    for p in system_private_prompts:
        is_active = "🔹" if p.id == active_prompt_id_in_session else "▪️"
        display_name = f"{is_active} {p.name} (系统预设)"
        categorized_prompts.append((p, display_name, False))

    user_prompt_ids_already_listed = {p[0].id for p in categorized_prompts}  # Track IDs to avoid duplicates

    for p in user_private_prompts:
        if p.id in user_prompt_ids_already_listed:  # Should not happen if system prompts are distinct
            continue
        is_active = "🔹" if p.id == active_prompt_id_in_session else "▪️"
        display_name = f"{is_active} {p.name}"
        categorized_prompts.append((p, display_name, True))

    if not categorized_prompts:
        keyboard = [[InlineKeyboardButton("➕ 创建新私人角色", callback_data=CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT)]]
        return InlineKeyboardMarkup(keyboard), "你还没有可用的私人角色。\n点击下方按钮创建一个吧！"

    total_prompts = len(categorized_prompts)
    total_pages = math.ceil(total_prompts / PROMPTS_PER_PAGE)
    current_page = max(0, min(page, total_pages - 1))

    start_index = current_page * PROMPTS_PER_PAGE
    end_index = start_index + PROMPTS_PER_PAGE
    prompts_to_display = categorized_prompts[start_index:end_index]

    keyboard_rows: list[list[InlineKeyboardButton]] = []

    for prompt, display_name_with_marker, is_user_prompt in prompts_to_display:
        row_buttons = []

        button_text = display_name_with_marker
        if len(button_text.encode('utf-8')) > 30:  # Max length for the main button
            button_text = button_text[:10] + "..."

        # Main button for selection
        row_buttons.append(
            InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT}{prompt.id}"))

        if is_user_prompt and not prompt.is_system_default:
            row_buttons.append(
                InlineKeyboardButton("✏️ 编辑", callback_data=f"{CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT}{prompt.id}"))
            row_buttons.append(
                InlineKeyboardButton("🗑️ 删除", callback_data=f"{CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT}{prompt.id}"))
        elif prompt.is_system_default:
            # Add a couple of non-clickable placeholders or fewer buttons to help alignment if needed
            # For simplicity, we can just have fewer buttons for system prompts.
            pass  # System prompts only get the main select button in this layout

        keyboard_rows.append(row_buttons)

    nav_row: list[InlineKeyboardButton] = []
    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton("⬅️ 上一页", callback_data=f"{CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE}{current_page - 1}"))

    if total_pages > 1:  # Only show page indicator if there's more than one page
        nav_row.append(
            InlineKeyboardButton(f"第 {current_page + 1}/{total_pages} 页", callback_data=CALLBACK_NOOP_PAGE_INDICATOR))

    if end_index < total_prompts:
        nav_row.append(
            InlineKeyboardButton("下一页 ➡️", callback_data=f"{CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE}{current_page + 1}"))

    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append(
        [InlineKeyboardButton("➕ 创建新私人角色", callback_data=CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT)])

    message_text = f"请选择或管理你的私人角色 (第 {current_page + 1}/{total_pages} 页):\n🔹 表示当前激活的角色。"
    return InlineKeyboardMarkup(keyboard_rows), message_text


# --- Command Handler for /my_prompts ---
async def my_prompts_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /my_prompts command by displaying the first page of private prompts."""
    if not update.effective_user:
        log.warning("Cannot execute /my_prompts: no effective_user.")
        if update.message:
            await update.message.reply_text("无法识别用户信息，请重试。")
        return

    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} requested /my_prompts (initial page).")

    if update.effective_chat:  # Check if effective_chat is available
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    else:
        log.warning("Cannot send chat action for /my_prompts: no effective_chat.")

    reply_markup, message_text = await _generate_my_prompts_keyboard(user_id, page=0)

    if update.message:
        if reply_markup:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(message_text)
