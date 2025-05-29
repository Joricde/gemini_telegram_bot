# gemini-telegram-bot/bot/telegram_adapter/conversations/private_prompt_edit.py

from typing import Optional, Dict

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler  # Needed for the entry point
)
from telegram.constants import ParseMode, ChatAction

from bot.utils import log
from bot.message_processing.prompt_manager import (
    EDIT_PRIVATE_INSTRUCTION,  # State
    start_edit_private_prompt_flow,  # To start the flow
    received_new_instruction_for_edit,
    # cancel_prompt_operation # Used by common cancel handler
)
from .common import cancel_conversation_command_handler  # Import common cancel handler

# Import the callback prefix for editing, ensure it's accessible
# This might come from ..commands, ..callbacks, or a new ..constants file
# For now, let's assume it's available or define it for clarity if not imported
# Example: from ..commands import CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT
# If not, define it temporarily for this file:
CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT = "pr_edit:"  # Make sure this matches the one used in commands.py


# --- Entry Point for Edit Conversation ---
async def edit_prompt_entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Entry point for starting the edit private prompt conversation via callback."""
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        log.warning("Edit prompt entry point: missing query, data, or user.")
        if query: await query.answer()  # Answer callback if possible
        return ConversationHandler.END

    await query.answer()
    user_id = str(update.effective_user.id)

    try:
        prompt_id_str = query.data.split(CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT, 1)[1]
        prompt_id_to_edit = int(prompt_id_str)
    except (IndexError, ValueError):
        log.error(f"Invalid callback data for edit prompt entry: {query.data}")
        await query.edit_message_text("无法开始编辑：无效的请求。")
        return ConversationHandler.END

    log.info(f"User {user_id} starting private prompt edit process for prompt ID {prompt_id_to_edit} via entry point.")

    if context.user_data is None:
        context.user_data = {}

    # This function (start_edit_private_prompt_flow) sends the first message
    # and stores prompt_id_to_edit in context.user_data
    response_text = await start_edit_private_prompt_flow(user_id, prompt_id_to_edit, context.user_data)

    # The message is edited by start_edit_private_prompt_flow usually via the initial callback handler.
    # If this entry point is hit directly, we need to ensure the message is sent/edited.
    # The private_prompts_callback_handler in callbacks.py already does this.
    # This entry point primarily sets the state. The message edit is already done.
    if query.message:  # If the original message still exists
        try:
            # The message should have been edited by the calling callback handler
            # or start_edit_private_prompt_flow itself if it was designed to.
            # For robustness, we can ensure it is by editing again, or trust the flow.
            # For now, we trust the calling callback in callbacks.py handled the message edit.
            # If start_edit_private_prompt_flow sends a message, this edit_message_text might conflict or be redundant.
            # The original design in callbacks.py had it call start_edit_private_prompt_flow and then edit the message with its response.
            # Let's assume that flow is correct and this entry point is just for state transition.
            # The message displayed to the user "You are editing..." is sent by start_edit_private_prompt_flow.
            await query.edit_message_text(text=response_text, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            log.error(f"Error editing message in edit_prompt_entry_point: {e}")
            # If editing fails, try sending a new message
            if update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text,
                                               parse_mode=ParseMode.MARKDOWN)

    return EDIT_PRIVATE_INSTRUCTION


# --- State Handler for Edit Conversation ---
async def private_instruction_handler_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the new system instruction during private prompt editing."""
    # ... (this function remains the same as previously defined)
    if not update.effective_user or not update.message or not update.message.text:
        if update.message:
            await update.message.reply_text("消息无效，请重试或使用 /cancel 取消。")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    new_instruction = update.message.text
    log.debug(f"User {user_id} provided new system instruction for editing: '{new_instruction[:50]}...'")

    if context.user_data is None or 'prompt_id_to_edit' not in context.user_data:
        await update.message.reply_text(
            "发生内部错误（编辑目标丢失），请重新从 /my_prompts 选择角色进行编辑，或使用 /cancel 取消。")
        return ConversationHandler.END

    response_text = await received_new_instruction_for_edit(user_id, new_instruction, context.user_data)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)
    context.user_data.clear()
    return ConversationHandler.END


# --- ConversationHandler Definition ---
edit_private_prompt_conversation_handler = ConversationHandler(
    entry_points=[
        # This CallbackQueryHandler now explicitly defines the entry for this conversation.
        # The pattern should match the "Edit" button's callback_data.
        CallbackQueryHandler(edit_prompt_entry_point, pattern=f"^{CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT}(\\d+)$")
    ],
    states={
        EDIT_PRIVATE_INSTRUCTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, private_instruction_handler_for_edit)],
    },
    fallbacks=[CommandHandler("cancel", cancel_conversation_command_handler)],
)