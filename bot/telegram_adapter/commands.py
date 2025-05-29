# gemini-telegram-bot/bot/telegram_adapter/commands.py

import math
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, \
    CommandHandler, MessageHandler, filters  # Added ConversationHandler for return type hint
from telegram.constants import ChatAction, ParseMode

from bot.message_processing import prompt_manager
from bot.utils import log, is_user_group_admin
from bot.database import SessionLocal
from bot.database import models as db_models  # For type hinting Prompt objects
from bot.database.models import PromptType
from bot.database.crud import (
    get_prompts_by_user_and_type,
    get_system_default_prompts,
    get_active_chat_session_state,
    get_prompt_by_id_and_user,  # For /set_prompt
    get_prompt_by_name_and_user,  # For /set_prompt by name (optional advanced)
    get_system_prompt_by_name  # For /set_prompt system by name (optional advanced)
)
# Import functions and states for conversation from prompt_manager
from bot.message_processing.prompt_manager import (
    start_upload_private_prompt_flow,
    UPLOAD_PRIVATE_INSTRUCTION,  # Conversation state
    set_active_private_prompt, cancel_prompt_operation  # For /set_prompt by ID
)

from bot.message_processing import group_chat as group_chat_processor  # For set_group_chat_mode


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
        is_active = "✅" if p.id == active_prompt_id_in_session else "➖"  # Using ➖ for inactive consistency
        display_name = f"{is_active} {p.name} (系统预设)"
        categorized_prompts.append((p, display_name, False))  # False indicates not user-editable/deletable

    user_prompt_ids_already_listed = {p[0].id for p in categorized_prompts}

    for p in user_private_prompts:
        if p.id in user_prompt_ids_already_listed:
            continue
        is_active = "✅" if p.id == active_prompt_id_in_session else "➖"
        display_name = f"{is_active} {p.name}"
        categorized_prompts.append((p, display_name, True))  # True indicates user-editable/deletable

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

    for prompt, display_name_with_marker, is_user_prompt_actions_enabled in prompts_to_display:
        row_buttons = []

        button_text = display_name_with_marker
        # Simple truncation for button text; consider byte length if using many CJK characters
        max_display_chars = 15  # Adjust as needed for typical prompt names
        if len(button_text) > max_display_chars:
            button_text = button_text[:max_display_chars - 1] + "…"

        row_buttons.append(
            InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT}{prompt.id}"))

        if is_user_prompt_actions_enabled and not prompt.is_system_default:  # Ensure it's not a system default for edit/delete
            row_buttons.append(
                InlineKeyboardButton("✏️ 编辑", callback_data=f"{CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT}{prompt.id}"))
            row_buttons.append(
                InlineKeyboardButton("🗑️ 删除", callback_data=f"{CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT}{prompt.id}"))
        elif prompt.is_system_default:
            # System prompts only get the select button in this row
            pass

        keyboard_rows.append(row_buttons)

    nav_row: list[InlineKeyboardButton] = []
    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton("⬅️ 上一页", callback_data=f"{CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE}{current_page - 1}"))

    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(f"第 {current_page + 1}/{total_pages} 页", callback_data=CALLBACK_NOOP_PAGE_INDICATOR))

    if end_index < total_prompts:
        nav_row.append(
            InlineKeyboardButton("下一页 ➡️", callback_data=f"{CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE}{current_page + 1}"))

    if nav_row:
        keyboard_rows.append(nav_row)

    keyboard_rows.append(
        [InlineKeyboardButton("➕ 创建新私人角色", callback_data=CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT)])

    message_text = f"请选择或管理你的私人角色 (第 {current_page + 1}/{total_pages} 页):\n✅ 表示当前激活, ➖ 表示可用但未激活。"
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

    chat_id_to_use = None
    if update.message and update.message.chat:
        chat_id_to_use = update.message.chat.id
    elif update.effective_chat:
        chat_id_to_use = update.effective_chat.id

    if chat_id_to_use:
        await context.bot.send_chat_action(chat_id=chat_id_to_use, action=ChatAction.TYPING)
    else:
        log.warning("Cannot send chat action for /my_prompts: no effective_chat or message.chat.")

    reply_markup, message_text = await _generate_my_prompts_keyboard(user_id, page=0)

    if update.message:
        if reply_markup:
            await update.message.reply_text(message_text, reply_markup=reply_markup, )
        else:
            await update.message.reply_text(message_text,
                                            )  # ensure markdown for consistency
    elif chat_id_to_use:  # Fallback if update.message is somehow None but we have a chat_id
        log.warning("update.message is None for /my_prompts. Sending new message to chat_id_to_use.")
        if reply_markup:
            await context.bot.send_message(chat_id_to_use, text=message_text, reply_markup=reply_markup,
                                           )
        else:
            await context.bot.send_message(chat_id_to_use, text=message_text, )


# --- Command Handler for /upload_prompt (Entry point for ConversationHandler) ---
async def upload_prompt_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """
    Handles the /upload_prompt command.
    This is an entry point for a ConversationHandler that manages prompt creation.
    """
    if not update.effective_user:
        log.warning("Cannot execute /upload_prompt: no effective_user.")
        if update.message: await update.message.reply_text("无法识别用户信息，请重试。")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} initiated /upload_prompt.")

    if update.message and update.message.chat:
        await context.bot.send_chat_action(chat_id=update.message.chat.id, action=ChatAction.TYPING)

    if context.user_data is None:  # Ensure user_data dictionary exists
        context.user_data = {}

    response_text = await start_upload_private_prompt_flow(user_id, context.user_data)

    if update.message:
        await update.message.reply_text(response_text, )
    else:  # Should not happen for a command
        log.error("update.message is None in upload_prompt_command_handler")
        return ConversationHandler.END

    return UPLOAD_PRIVATE_INSTRUCTION  # Next state in the conversation


async def cancel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /cancel command to abort ongoing conversations."""
    if not update.effective_user:
        if update.message: await update.message.reply_text("无法识别用户。")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} triggered /cancel for a conversation.")

    if context.user_data is None:
        context.user_data = {}  # Should ideally exist if in a conversation

    response_text = await cancel_prompt_operation(user_id, context.user_data)  # This clears user_data
    if update.message:
        await update.message.reply_text(response_text)
    else:  # If /cancel was somehow triggered by a callback button (not typical for this command)
        if update.callback_query and update.callback_query.message:
            await update.callback_query.edit_message_text(response_text)  # Clean up the message with buttons
        elif update.effective_chat:  # Fallback to send new message
            await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text)

    return ConversationHandler.END




CALLBACK_PREFIX_GROUP_MODE = "grp_mode:" # 你可以将这个常量移到更中心的位置，如果多处用到

async def mode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /mode command. Sends buttons for admins to switch group chat mode.
    """
    if not update.effective_chat or not update.message or not update.effective_user:
        log.warning("Mode command: effective_chat, message, or effective_user missing.")
        return

    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("此命令只能在群组或超级群组中使用。")
        return

    if not await is_user_group_admin(update, context):
        log.info(f"User {update.effective_user.id} tried to use /mode in group {update.effective_chat.id} without admin rights.")
        await update.message.reply_text("抱歉，只有群管理员才能更改群聊模式。")
        return

    # 不再解析 context.args，而是发送按钮
    keyboard = [
        [
            InlineKeyboardButton("设置为 独立会话 (Individual) 模式", callback_data=f"{CALLBACK_PREFIX_GROUP_MODE}individual"),
        ],
        [
            InlineKeyboardButton("设置为 共享会话 (Shared) 模式", callback_data=f"{CALLBACK_PREFIX_GROUP_MODE}shared"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("请选择要设置的群聊模式：", reply_markup=reply_markup)


# bot/telegram_adapter/commands.py

# ... (现有 imports) ...
from bot.utils import log, is_user_group_admin
from bot.message_processing import group_chat as group_chat_processor  # For set_group_shared_role_prompt


# ... (其他 command handlers, CALLBACK_PREFIX_GROUP_MODE etc.) ...

async def set_group_prompt_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the /set_group_prompt command for admins to set the shared mode prompt.
    Usage: /set_group_prompt <prompt_id_or_system_name>
    """
    if not update.effective_chat or not update.message or not update.effective_user:
        log.warning("Set_group_prompt command: effective_chat, message, or effective_user missing.")
        return

    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("此命令只能在群组或超级群组中使用。")
        return

    if not await is_user_group_admin(update, context):
        log.info(
            f"User {update.effective_user.id} tried to use /set_group_prompt in group {update.effective_chat.id} without admin rights.")
        await update.message.reply_text("抱歉，只有群管理员才能设置群聊共享角色。")
        return

    if not context.args:  # Require at least one argument
        await update.message.reply_text(
            "请提供一个角色ID或系统预设的角色名称。\n"
            "用法: `/set_group_prompt <角色ID或名称>`\n"
            "例如: `/set_group_prompt 中立群成员` 或 `/set_group_prompt 2` (假设2是一个有效的群聊角色ID)"
        )
        return

    prompt_identifier_arg = " ".join(context.args)  # Allow names with spaces
    group_id_str = str(update.effective_chat.id)

    log.info(
        f"Admin {update.effective_user.id} attempting to set shared prompt to '{prompt_identifier_arg}' for group {group_id_str}.")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    response_message_text = await group_chat_processor.set_group_shared_role_prompt(group_id_str, prompt_identifier_arg)

    await update.message.reply_text(response_message_text, parse_mode=ParseMode.MARKDOWN)
