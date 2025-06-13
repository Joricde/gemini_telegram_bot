# bot/telegram/handlers/messages.py
from telegram import Update, constants
from telegram.ext import ContextTypes

from bot.services.chat_service import ChatService
from bot.core.logging import logger


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles all non-command text messages and routes them to the appropriate service.
    """
    # Ignore empty messages
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text

    logger.info(f"Message received from user {user.id} in chat {chat.id} ({chat.type})")

    # Show "typing..." action to the user
    await context.bot.send_chat_action(chat_id=chat.id, action=constants.ChatAction.TYPING)

    # Retrieve the chat service from context
    chat_service: ChatService = context.bot_data["chat_service"]

    response = None
    try:
        # Route to the correct service method based on chat type
        if chat.type == constants.ChatType.PRIVATE:
            response = await chat_service.handle_private_message(user_data=user, text=text)
        elif chat.type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP]:
            # Check if the bot was mentioned
            bot_username = context.bot.username
            is_mention = any(
                e.type == constants.MessageEntityType.MENTION and text[
                                                                  e.offset:e.offset + e.length] == f"@{bot_username}"
                for e in update.message.entities
            )
            response = await chat_service.handle_group_message(
                chat_id=chat.id,
                user_data=user,
                text=text,
                is_mention=is_mention
            )

        # If the service returned a response, send it
        if response:
            await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error handling message in chat {chat.id}: {e}", exc_info=True)
        await update.message.reply_text("I'm sorry, an unexpected error occurred. Please try again later.")
