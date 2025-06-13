# bot/telegram/handlers/conversations.py
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)

from bot.services.prompt_service import PromptService
from bot.core.logging import logger

# Define the states for our conversation
TITLE, PROMPT_TEXT = range(2)


async def add_prompt_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Starts the conversation to add a new prompt. Asks for the title.
    This function is triggered by a CallbackQueryHandler.
    """
    query = update.callback_query
    await query.answer()  # Answer the callback query

    logger.info(f"User {query.from_user.id} starting to add a new prompt.")
    await query.edit_message_text(
        "Okay, let's create a new persona! What should its title be? (e.g., 'Helpful Assistant', 'Sarcastic Friend')")

    # Tell ConversationHandler that we are now in the TITLE state
    return TITLE


async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receives the title from the user, saves it temporarily, and asks for the prompt text.
    """
    user_id = update.effective_user.id
    title = update.message.text

    # Store the title temporarily in context.user_data.
    # This dictionary is persistent for the user across the conversation.
    context.user_data['new_prompt_title'] = title

    logger.info(f"User {user_id} provided title for new prompt: '{title}'")
    await update.message.reply_text(
        f"Great! The title is '{title}'.\n\n"
        "Now, please send me the full text for this persona. This is the system instruction that will guide my responses."
    )

    # Move to the next state, PROMPT_TEXT
    return PROMPT_TEXT


async def receive_prompt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """

    Receives the prompt text, creates the prompt in the database, and ends the conversation.
    """
    user_id = update.effective_user.id
    prompt_text = update.message.text

    # Retrieve the title we saved in the previous step
    title = context.user_data.get('new_prompt_title')

    if not title:
        logger.warning(f"User {user_id} reached receive_prompt_text without a title in user_data.")
        await update.message.reply_text("Something went wrong. Let's start over.")
        return ConversationHandler.END

    prompt_service: PromptService = context.bot_data["prompt_service"]

    # Use the service to create the new prompt
    new_prompt = prompt_service.create_new_prompt(user_id=user_id, title=title, text=prompt_text)

    if new_prompt:
        await update.message.reply_text(f"✅ Success! Your new persona '{title}' has been saved.")
    else:
        await update.message.reply_text("❌ I'm sorry, there was an error saving your prompt. Please try again later.")

    # Clean up the temporary data
    del context.user_data['new_prompt_title']

    # End the conversation
    logger.info(f"User {user_id} finished adding a new prompt.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the entire conversation.
    """
    user = update.effective_user
    logger.info(f"User {user.id} canceled the conversation.")

    # Clean up any temporary data
    if 'new_prompt_title' in context.user_data:
        del context.user_data['new_prompt_title']

    await update.message.reply_text("Operation canceled.")

    return ConversationHandler.END


# Assemble the ConversationHandler
add_prompt_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_prompt_start, pattern="^add_new_prompt$")],
    states={
        TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
        PROMPT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt_text)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    conversation_timeout=300  # Timeout in seconds
)