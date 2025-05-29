# gemini-telegram-bot/bot/telegram_adapter/callbacks.py

from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.utils import log
from .commands import (
    _generate_my_prompts_keyboard,
    CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE,
    CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT,
    CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT,
    CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT,
    CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT,
    CALLBACK_NOOP_PAGE_INDICATOR
)
from bot.message_processing.prompt_manager import (
    set_active_private_prompt,
    confirm_delete_private_prompt,
    start_edit_private_prompt_flow,
    start_upload_private_prompt_flow,
    UPLOAD_PRIVATE_INSTRUCTION,
    EDIT_PRIVATE_INSTRUCTION
)


async def private_prompts_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handles button presses from the /my_prompts keyboard."""
    query = update.callback_query

    if not query:
        log.warning("CallbackQuery object is None in private_prompts_callback_handler.")
        return None

    await query.answer()

    user = update.effective_user
    if not user:
        log.warning("No effective_user in private_prompts_callback_handler.")
        if query.message:  # Try to edit if possible
            try:
                await query.edit_message_text(text="无法识别用户，请重试。")
            except Exception as e_edit:
                log.error(f"Failed to edit message on user recognition failure: {e_edit}")
        return None

    user_id = str(user.id)
    callback_data = query.data

    if not callback_data:
        log.warning(f"User {user_id} sent an empty callback_data.")
        return None

    if context.user_data is None:
        context.user_data = {}

    next_conversation_state: Optional[int] = None

    # Determine chat_id for actions. This is crucial.
    chat_id_for_actions: Optional[int] = None
    if query.message and query.message.chat:
        chat_id_for_actions = query.message.chat.id

    # If we can't get a chat_id, many operations will fail.
    # For operations that don't strictly need to interact with the original message's chat
    # (like some background DB updates), this might be less critical, but most UI updates need it.
    if not chat_id_for_actions:
        log.error(
            f"Could not determine chat_id from query.message for user {user_id}, callback '{callback_data}'. Original message might be inaccessible.")
        # We can't edit the message or send a new one to the original chat without a chat_id.
        # We could potentially PM the user if query.from_user.id is available.
        # For now, we log and might have to abort some UI updates.
        # Some actions might still proceed if they don't need to update the specific message.

    # --- Pagination ---
    if callback_data.startswith(CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE):
        try:
            page_str = callback_data.split(CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE, 1)[1]
            page = int(page_str)
            log.info(f"User {user_id} navigating to private prompts page {page}.")

            if chat_id_for_actions:  # Only send chat action if we have a chat_id
                await context.bot.send_chat_action(chat_id=chat_id_for_actions, action=ChatAction.TYPING)

            reply_markup, message_text = await _generate_my_prompts_keyboard(user_id, page=page)

            if query.message:  # edit_message_text requires query.message
                if reply_markup:
                    await query.edit_message_text(text=message_text, reply_markup=reply_markup)
                else:
                    await query.edit_message_text(text=message_text)
            elif chat_id_for_actions:  # Fallback if original message is gone but we have chat_id
                log.warning("query.message is None for pagination. Sending new message.")
                await context.bot.send_message(chat_id=chat_id_for_actions, text=message_text,
                                               reply_markup=reply_markup)
            else:
                log.error("Cannot update UI for pagination: no query.message and no chat_id_for_actions.")

        except (IndexError, ValueError) as e:
            log.error(f"Error parsing page number from callback_data '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="翻页时数据错误，请重试。")

    # --- Select Prompt ---
    elif callback_data.startswith(CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT):
        try:
            prompt_id_str = callback_data.split(CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT, 1)[1]
            prompt_id = int(prompt_id_str)
            log.info(f"User {user_id} selected private prompt ID {prompt_id} to activate.")

            if chat_id_for_actions:
                await context.bot.send_chat_action(chat_id=chat_id_for_actions, action=ChatAction.TYPING)

            response_text = await set_active_private_prompt(user_id, prompt_id)

            message_edited_or_sent = False
            if query.message:
                await query.edit_message_text(text=response_text)  # Show confirmation
                message_edited_or_sent = True
                if chat_id_for_actions:  # Refresh keyboard
                    await context.bot.send_chat_action(chat_id=chat_id_for_actions, action=ChatAction.TYPING)
                reply_markup, message_text_refreshed = await _generate_my_prompts_keyboard(user_id, page=0)
                if reply_markup:
                    await query.edit_message_text(text=message_text_refreshed, reply_markup=reply_markup)

            if not message_edited_or_sent and chat_id_for_actions:  # Fallback if original message is gone
                log.warning("query.message is None for select prompt. Sending new messages.")
                await context.bot.send_message(chat_id=chat_id_for_actions, text=response_text)
                await context.bot.send_chat_action(chat_id=chat_id_for_actions, action=ChatAction.TYPING)
                reply_markup, message_text_refreshed = await _generate_my_prompts_keyboard(user_id, page=0)
                await context.bot.send_message(chat_id=chat_id_for_actions, text=message_text_refreshed,
                                               reply_markup=reply_markup)
            elif not chat_id_for_actions:
                log.error("Cannot update UI for select prompt: no query.message and no chat_id_for_actions.")

        except (IndexError, ValueError) as e:
            log.error(f"Error parsing prompt_id for selection from callback_data '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="选择角色时数据错误，请重试。")

    # --- Edit Prompt (Initiate Conversation) ---
    elif callback_data.startswith(CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT):
        try:
            prompt_id_str = callback_data.split(CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT, 1)[1]
            prompt_id_to_edit = int(prompt_id_str)
            log.info(f"User {user_id} chose to edit private prompt ID {prompt_id_to_edit}.")

            response_text = await start_edit_private_prompt_flow(user_id, prompt_id_to_edit, context.user_data)
            if query.message:
                await query.edit_message_text(text=response_text)
            elif chat_id_for_actions:
                log.warning("query.message is None for edit prompt start. Sending new message.")
                await context.bot.send_message(chat_id=chat_id_for_actions, text=response_text)
            else:
                log.error("Cannot start edit flow UI: no query.message and no chat_id_for_actions.")
            next_conversation_state = EDIT_PRIVATE_INSTRUCTION
        except (IndexError, ValueError) as e:
            log.error(f"Error parsing prompt_id for edit from callback_data '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="编辑角色时数据错误，请重试。")

    # --- Delete Prompt ---
    elif callback_data.startswith(CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT):
        try:
            prompt_id_str = callback_data.split(CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT, 1)[1]
            prompt_id_to_delete = int(prompt_id_str)
            log.info(f"User {user_id} chose to delete private prompt ID {prompt_id_to_delete}.")

            if chat_id_for_actions:
                await context.bot.send_chat_action(chat_id=chat_id_for_actions, action=ChatAction.TYPING)

            response_text = await confirm_delete_private_prompt(user_id, prompt_id_to_delete)

            message_edited_or_sent = False
            if query.message:
                await query.edit_message_text(text=response_text)
                message_edited_or_sent = True

            if not message_edited_or_sent and chat_id_for_actions:
                log.warning("query.message is None for delete confirmation. Sending new message for result.")
                await context.bot.send_message(chat_id=chat_id_for_actions, text=response_text)
            elif not chat_id_for_actions:
                log.error("Cannot show delete confirmation: no query.message and no chat_id_for_actions.")

            if chat_id_for_actions:  # Refresh list in a new message
                await context.bot.send_chat_action(chat_id=chat_id_for_actions, action=ChatAction.TYPING)
                reply_markup, new_message_text = await _generate_my_prompts_keyboard(user_id, page=0)
                await context.bot.send_message(chat_id=chat_id_for_actions, text=new_message_text,
                                               reply_markup=reply_markup)
            else:
                log.error("Cannot send refreshed prompt list after delete: no chat_id_for_actions.")

        except (IndexError, ValueError) as e:
            log.error(f"Error parsing prompt_id for delete from callback_data '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="删除角色时数据错误，请重试。")

    # --- Create New Private Prompt (Initiate Conversation) ---
    elif callback_data == CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT:
        log.info(f"User {user_id} chose to create a new private prompt via button.")
        response_text = await start_upload_private_prompt_flow(user_id, context.user_data)
        if query.message:
            await query.edit_message_text(text=response_text)
        elif chat_id_for_actions:
            log.warning("query.message is None for create prompt start. Sending new message.")
            await context.bot.send_message(chat_id=chat_id_for_actions, text=response_text)
        else:
            log.error("Cannot start create flow UI: no query.message and no chat_id_for_actions.")
        next_conversation_state = UPLOAD_PRIVATE_INSTRUCTION

    elif callback_data == CALLBACK_NOOP_PAGE_INDICATOR:
        pass
    else:
        log.warning(f"User {user_id} sent unhandled callback_data: {callback_data}")
        if query.message: await query.edit_message_text(text="未知操作。")

    return next_conversation_state
