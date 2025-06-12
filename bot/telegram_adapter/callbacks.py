# bot/telegram_adapter/callbacks.py

from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.utils import log
from .commands import (  # Assuming _generate_my_prompts_keyboard is still in commands.py
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
    start_edit_private_prompt_flow,  # Import this
    start_upload_private_prompt_flow,
    UPLOAD_PRIVATE_INSTRUCTION,  # For create flow
    EDIT_PRIVATE_INSTRUCTION  # Import this for edit flow
)


async def private_prompts_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handles button presses from the /my_prompts keyboard."""
    query = update.callback_query
    if not query:
        log.warning("CallbackQuery object is None in private_prompts_callback_handler.")
        return None

    await query.answer()  # Answer callback query quickly

    user = update.effective_user
    if not user:
        log.warning("No effective_user in private_prompts_callback_handler.")
        if query.message:
            try:
                await query.edit_message_text(text="无法识别用户，请重试。")
            except Exception as e_edit:
                log.error(f"Failed to edit message on user recognition failure: {e_edit}")
        return None  # End conversation or current processing

    user_id = str(user.id)
    callback_data = query.data

    if not callback_data:
        log.warning(f"User {user_id} sent an empty callback_data.")
        return None

    # Ensure user_data exists, it's crucial for ConversationHandler
    if context.user_data is None:
        context.user_data = {}

    next_conversation_state: Optional[int] = None  # Default to no state change / end conversation

    chat_id_for_actions: Optional[int] = None
    if query.message and query.message.chat:
        chat_id_for_actions = query.message.chat.id

    if not chat_id_for_actions:
        log.error(f"User {user_id}, callback '{callback_data}': Could not determine chat_id. Aborting UI updates.")
        # Depending on the action, we might still proceed if no UI update to the original message is needed.
        # For now, most actions below assume they will edit query.message or send to chat_id_for_actions.

    # --- Pagination ---
    if callback_data.startswith(CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE):
        try:
            page_str = callback_data.split(CALLBACK_PREFIX_PRIVATE_PROMPT_PAGE, 1)[1]
            page = int(page_str)
            log.info(f"User {user_id} navigating to private prompts page {page}.")
            if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                       action=ChatAction.TYPING)

            reply_markup, message_text = await _generate_my_prompts_keyboard(user_id, page=page)
            if query.message:  # Necessary for edit_message_text
                await query.edit_message_text(text=message_text, reply_markup=reply_markup)
            elif chat_id_for_actions:  # Fallback: send new if original message gone
                await context.bot.send_message(chat_id_for_actions, text=message_text, reply_markup=reply_markup)

        except (IndexError, ValueError) as e:
            log.error(f"Error parsing page number from callback_data '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="翻页时数据错误，请重试。")

    # --- Select Prompt ---
    elif callback_data.startswith(CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT):
        try:
            prompt_id_str = callback_data.split(CALLBACK_PREFIX_SELECT_PRIVATE_PROMPT, 1)[1]
            prompt_id = int(prompt_id_str)
            log.info(f"User {user_id} selected private prompt ID {prompt_id} to activate.")
            if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                       action=ChatAction.TYPING)

            response_text = await set_active_private_prompt(user_id, prompt_id)

            # Edit the current message to show confirmation, then refresh the list
            if query.message:
                await query.edit_message_text(text=response_text)  # Show confirmation first
                # Now refresh the keyboard in the same message
                if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                           action=ChatAction.TYPING)
                reply_markup, new_message_text = await _generate_my_prompts_keyboard(user_id,
                                                                                     page=0)  # Refresh to page 0 or current page
                await query.edit_message_text(text=new_message_text, reply_markup=reply_markup)

            elif chat_id_for_actions:  # Fallback if original message is gone
                await context.bot.send_message(chat_id_for_actions, text=response_text)
                if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                           action=ChatAction.TYPING)
                reply_markup, new_message_text = await _generate_my_prompts_keyboard(user_id, page=0)
                await context.bot.send_message(chat_id_for_actions, text=new_message_text, reply_markup=reply_markup)


        except (IndexError, ValueError) as e:
            log.error(f"Error parsing prompt_id for selection from '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="选择角色时数据错误，请重试。")


    # --- Delete Prompt ---
    elif callback_data.startswith(CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT):
        try:
            prompt_id_str = callback_data.split(CALLBACK_PREFIX_DELETE_PRIVATE_PROMPT, 1)[1]
            prompt_id_to_delete = int(prompt_id_str)
            log.info(f"User {user_id} chose to delete private prompt ID {prompt_id_to_delete}.")
            if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                       action=ChatAction.TYPING)

            response_text = await confirm_delete_private_prompt(user_id, prompt_id_to_delete)

            # Show confirmation, then refresh list
            if query.message:
                await query.edit_message_text(text=response_text)  # Show result of deletion
                if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                           action=ChatAction.TYPING)
                # Refresh the list in the same message
                reply_markup, new_message_text = await _generate_my_prompts_keyboard(user_id, page=0)  # Refresh page
                await query.edit_message_text(text=new_message_text, reply_markup=reply_markup)
            elif chat_id_for_actions:  # Fallback
                await context.bot.send_message(chat_id_for_actions, text=response_text)
                if chat_id_for_actions: await context.bot.send_chat_action(chat_id=chat_id_for_actions,
                                                                           action=ChatAction.TYPING)
                reply_markup, new_message_text = await _generate_my_prompts_keyboard(user_id, page=0)
                await context.bot.send_message(chat_id_for_actions, text=new_message_text, reply_markup=reply_markup)

        except (IndexError, ValueError) as e:
            log.error(f"Error parsing prompt_id for delete from '{callback_data}': {e}")
            if query.message: await query.edit_message_text(text="删除角色时数据错误，请重试。")

    # --- Create New Private Prompt (Initiate Conversation via button) ---
    elif callback_data == CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT:
        log.info(f"User {user_id} chose to create a new private prompt via button.")
        # Call prompt_manager to start the upload flow
        response_text = await start_upload_private_prompt_flow(user_id, context.user_data)
        if query.message:
            await query.edit_message_text(text=response_text)  # Edit current message to start the flow
        elif chat_id_for_actions:  # Fallback
            await context.bot.send_message(chat_id_for_actions, text=response_text)

        next_conversation_state = UPLOAD_PRIVATE_INSTRUCTION  # Return this state for create flow

    elif callback_data == CALLBACK_NOOP_PAGE_INDICATOR:
        pass  # No action needed, just answered the query
    else:
        log.warning(f"User {user_id} sent unhandled callback_data: {callback_data}")
        if query.message: await query.edit_message_text(text="未知操作。")

    log.debug(
        f"User {user_id} - private_prompts_callback_handler: Final state being returned: {next_conversation_state} for callback_data: {callback_data}")
    return next_conversation_state