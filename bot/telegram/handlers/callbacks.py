# bot/telegram/handlers/callbacks.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from bot.database import crud
from bot.telegram import keyboards
from bot.services.prompt_service import PromptService
from bot.core.logging import logger


# A helper function to avoid code duplication, as this menu is shown in multiple places.
async def show_prompt_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the prompt management menu to the user."""
    query = update.callback_query
    user_id = query.from_user.id

    prompt_service: PromptService = context.bot_data["prompt_service"]
    user_prompts = prompt_service.list_user_prompts(user_id=user_id)

    if not user_prompts:
        text = "You haven't created any custom prompts yet. Use the button below to add one."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("＋ Add New Prompt", callback_data="add_new_prompt")],
                                         [InlineKeyboardButton("« Back to Main Menu", callback_data="start_menu")]])
    else:
        text = "Here are your custom prompts. Click one to make it active, or ❌ to delete it."
        keyboard = keyboards.create_prompt_list_keyboard(user_prompts)

    await query.edit_message_text(text=text, reply_markup=keyboard)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Acts as a router for all button clicks (CallbackQuery).
    """
    query = update.callback_query
    # Always answer the callback query to remove the "loading" state in the user's client
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    logger.info(f"Callback query received from user {user_id}: {data}")

    # --- ROUTING LOGIC ---
    if data == "start_menu":
        welcome_text = (
            f"Hi {query.from_user.first_name}! I'm your personal Gemini assistant. "
            "Let's start chatting, or you can use the menu below to manage our conversation."
        )
        keyboard = keyboards.create_start_menu_keyboard()
        await query.edit_message_text(text=welcome_text, reply_markup=keyboard)

    elif data == "manage_prompts":
        await show_prompt_management_menu(update, context)

    elif data == "clear_history":
        crud.reset_session(db=context.bot_data["db_session"], chat_id=user_id)
        await query.edit_message_text("✨ Your conversation history has been cleared.")
        # We might want to show the main menu again after a delay
        # await asyncio.sleep(2)
        # ... show start menu ...

    elif data == "help_menu":
        # This can be expanded later
        await query.answer("Help is on the way! (Not yet implemented)", show_alert=True)

    elif data.startswith("select_prompt:"):
        try:
            prompt_id = int(data.split(":")[1])
            crud.set_active_prompt_for_user(db=context.bot_data["db_session"], user_id=user_id, prompt_id=prompt_id)
            await query.answer("Persona updated!", show_alert=False)
            # Refresh the menu to show the new checkmark
            await show_prompt_management_menu(update, context)
        except (ValueError, IndexError):
            logger.warning(f"Invalid callback data format: {data}")
            await query.answer("Invalid action.", show_alert=True)

    elif data.startswith("delete_prompt:"):
        try:
            prompt_id = int(data.split(":")[1])
            keyboard = keyboards.create_confirm_delete_keyboard(prompt_id)
            await query.edit_message_text(
                "Are you sure you want to delete this prompt?",
                reply_markup=keyboard
            )
        except (ValueError, IndexError):
            logger.warning(f"Invalid callback data format: {data}")

    elif data.startswith("confirm_delete_prompt:"):
        try:
            prompt_id = int(data.split(":")[1])
            prompt_service: PromptService = context.bot_data["prompt_service"]
            deleted = prompt_service.delete_user_prompt(user_id, prompt_id)
            if deleted:
                await query.answer("Prompt deleted.", show_alert=True)
            else:
                await query.answer("Could not delete prompt.", show_alert=True)
            await show_prompt_management_menu(update, context)
        except (ValueError, IndexError):
            logger.warning(f"Invalid callback data format: {data}")

    elif data.startswith("cancel_delete_prompt:"):
        await show_prompt_management_menu(update, context)

    # Placeholder for starting the add_prompt conversation
    elif data == "add_new_prompt":
        await query.edit_message_text("Let's create a new prompt! What should its title be?")
        # Here we will set the stage for the ConversationHandler
        # For now, this is just a placeholder.
