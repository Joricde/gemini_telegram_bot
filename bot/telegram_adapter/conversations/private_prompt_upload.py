# gemini-telegram-bot/bot/telegram_adapter/conversations/private_prompt_upload.py

from typing import Optional, Dict

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from telegram.constants import ParseMode

from bot.utils import log
# Assuming constants are defined in commands.py or a shared location.
# For now, direct import from commands.py for CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT
# This suggests constants might be better in a shared file.
from ..commands import CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT  # Relative import from sibling module

from bot.message_processing.prompt_manager import (
    cancel_prompt_operation  # General cancel operation
)

# At the top of private_prompt_upload.py
# ... other imports ...
from .common import cancel_conversation_command_handler # Import the common cancel handler
from bot.message_processing.prompt_manager import (
    UPLOAD_PRIVATE_INSTRUCTION, UPLOAD_PRIVATE_NAME, # States
    start_upload_private_prompt_flow,
    received_private_instruction_for_upload,
    received_private_prompt_name_and_create
    # cancel_prompt_operation is now used by the common handler, so not directly needed here unless for other purposes
)
# ... rest of the file ...

# --- Entry Point for Upload Conversation ---
async def upload_prompt_entry_point(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Common entry point for starting the upload prompt conversation via command or callback."""
    if not update.effective_user:
        log.warning("Cannot start prompt upload: no effective_user.")
        if update.message:
            await update.message.reply_text("无法识别用户信息，请重试。")
        elif update.callback_query:
            # If called via callback, the message might have already been edited by the callback handler.
            # However, if it directly enters here, we might need to edit.
            # For now, assume callback handler manages its initial message edit.
            # await update.callback_query.edit_message_text("无法识别用户信息，请重试。")
            log.info("User info missing for callback entry to upload_prompt_entry_point.")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    log.info(f"User {user_id} entering private prompt upload process.")

    if context.user_data is None:
        context.user_data = {}

    response_text = await start_upload_private_prompt_flow(user_id, context.user_data)

    if update.message:  # Called via /upload_prompt command
        await update.message.reply_text(response_text)
    elif update.callback_query:
        # If triggered by a callback (e.g., "Create New" button),
        # the calling callback handler (private_prompts_callback_handler)
        # should have already edited the message to show this initial response_text.
        # So, we primarily just return the state.
        log.debug("upload_prompt_entry_point called via CallbackQuery. Expecting message already edited.")
        pass

    return UPLOAD_PRIVATE_INSTRUCTION


# --- State Handlers for Upload Conversation ---
async def private_instruction_handler_for_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handles receiving the system instruction during private prompt upload."""
    if not update.effective_user or not update.message or not update.message.text:
        if update.message: await update.message.reply_text("消息无效，请重试或使用 /cancel 取消。")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    instruction = update.message.text
    log.debug(f"User {user_id} provided system instruction for new private prompt: '{instruction[:50]}...'")

    if context.user_data is None:  # Should have been initialized by entry point
        context.user_data = {}

    response_text = await received_private_instruction_for_upload(user_id, instruction, context.user_data)
    await update.message.reply_text(response_text)
    return UPLOAD_PRIVATE_NAME


async def private_name_handler_for_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the prompt name during private prompt upload and creates the prompt."""
    if not update.effective_user or not update.message or not update.message.text:
        if update.message: await update.message.reply_text("消息无效，请重试或使用 /cancel 取消。")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    name = update.message.text.strip()
    log.debug(f"User {user_id} provided name '{name}' for new private prompt.")

    if context.user_data is None:  # Should not happen if flow is correct
        await update.message.reply_text("发生内部错误（用户数据丢失），请重新开始 /upload_prompt。")
        return ConversationHandler.END

    response_text = await received_private_prompt_name_and_create(user_id, name, context.user_data)
    await update.message.reply_text(response_text)
    return ConversationHandler.END


# --- General Cancel Handler for Conversations ---
# This could be moved to a common conversations utility file if used by multiple conversation handlers.
async def cancel_conversation_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current ongoing conversation (e.g., prompt creation/editing)."""
    if not update.effective_user:
        # Cannot send message if no user/update context for it
        return ConversationHandler.END

    user_id = str(update.effective_user.id)
    if context.user_data is None:
        context.user_data = {}

    response_text = await cancel_prompt_operation(user_id, context.user_data)  # Clears context.user_data

    if update.message:  # If /cancel was sent as a command
        await update.message.reply_text(response_text)
    elif update.callback_query:  # If cancel was triggered by a button (not implemented here, but possible)
        await update.callback_query.edit_message_text(response_text)

    log.info(f"User {user_id} cancelled a conversation.")
    return ConversationHandler.END


# --- ConversationHandler Definition ---
# (At the end of bot/telegram_adapter/conversations/private_prompt_upload.py)

# --- ConversationHandler Definition ---
upload_private_prompt_conversation_handler = ConversationHandler(
    entry_points=[
        CommandHandler("upload_prompt", upload_prompt_entry_point),
        CallbackQueryHandler(upload_prompt_entry_point, pattern=f"^{CALLBACK_ACTION_CREATE_NEW_PRIVATE_PROMPT}$")
    ],
    states={
        UPLOAD_PRIVATE_INSTRUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, private_instruction_handler_for_upload)],
        UPLOAD_PRIVATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, private_name_handler_for_upload)],
    },
    fallbacks=[CommandHandler("cancel", cancel_conversation_command_handler)],
    # name="upload_private_prompt_conversation", # Optional: for persistence
    # persistent=False # Optional: for persistence
)
