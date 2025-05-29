# gemini-telegram-bot/bot/telegram_adapter/conversations/common.py

from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.utils import log
from bot.message_processing.prompt_manager import \
    cancel_prompt_operation  # Assuming this is the intended general cancel


async def cancel_conversation_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the current ongoing conversation (e.g., prompt creation/editing).
    This is a general handler intended to be used as a fallback in ConversationHandlers.
    """
    if not update.effective_user:
        # Cannot send message if no user/update context for it
        log.warning("cancel_conversation_command_handler called without effective_user.")
        return ConversationHandler.END

    user_id = str(update.effective_user.id)

    if context.user_data is None:
        context.user_data = {}

        # Call the core logic to clear any pending operation data
    response_text = await cancel_prompt_operation(user_id, context.user_data)

    if update.message:  # If /cancel was sent as a command
        await update.message.reply_text(response_text)
    elif update.callback_query:  # If cancel was triggered by a button (not typical for /cancel command)
        # This path is less common for a CommandHandler fallback, but included for completeness
        # if a cancel button were to use this same logic via a different mechanism.
        try:
            await update.callback_query.edit_message_text(response_text)
        except Exception as e:
            log.error(f"Error editing message on cancel callback: {e}. Sending new message.")
            if update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text)

    log.info(f"User {user_id} cancelled a conversation using /cancel or a cancel action.")
    return ConversationHandler.END
