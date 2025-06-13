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
    chat_id = update.effective_chat.id

    prompt_service: PromptService = context.bot_data["prompt_service"]
    db_session = context.bot_data["db_session"]

    # 1. Get all available prompts
    all_prompts = prompt_service.get_available_prompts()

    # 2. Get the active prompt key FOR THIS CHAT
    session = crud.get_or_create_session(db=db_session, chat_id=chat_id)
    active_key = session.active_prompt_key

    if not all_prompts:
        # This case is unlikely now with yaml prompts, but good to have
        text = "No prompts are available. Use the button below to add one."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("＋ Add New Prompt", callback_data="add_new_prompt")],
            [InlineKeyboardButton("« Back to Main Menu", callback_data="start_menu")]])
    else:
        text = "Here are the available personas. Click one to make it active for this chat, or ❌ to delete a shared one."
        # 3. Pass both lists to the keyboard builder
        keyboard = keyboards.create_prompt_list_keyboard(prompts=all_prompts, active_key=active_key)

    await query.edit_message_text(text=text, reply_markup=keyboard)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Acts as a router for all button clicks (CallbackQuery)."""
    query = update.callback_query
    await query.answer()

    # We need both user_id (for ownership/logging) and chat_id (for session state)
    user_id = query.from_user.id
    chat_id = update.effective_chat.id
    data = query.data

    logger.info(f"Callback query from user {user_id} in chat {chat_id}: {data}")

    # --- ROUTING LOGIC ---
    if data == "manage_prompts":
        await show_prompt_management_menu(update, context)

        # --- THIS IS THE MOST IMPORTANT FIX ---
    elif data.startswith("select_prompt:"):
        try:
            # The key is the full string, e.g., "db:123" or "yaml:default"
            prompt_key = data.split(":", 1)[1]

            # Pass the STRING key directly to the CRUD function
            crud.set_active_prompt_key_for_session(
                db=context.bot_data["db_session"],
                chat_id=chat_id,
                prompt_key=prompt_key  # Passing the correct 'str' type
            )
            await query.answer("Persona updated for this chat!", show_alert=False)
            # Refresh the menu to show the new checkmark
            await show_prompt_management_menu(update, context)
        except (ValueError, IndexError):
            logger.warning(f"Invalid callback data format for select: {data}")
            await query.answer("Invalid action.", show_alert=True)

    elif data.startswith("delete_prompt:"):
        # This logic should be mostly fine, just ensure it uses the correct service method
        try:
            prompt_id_str = data.split(":")[1]
            prompt_id = int(prompt_id_str)
            keyboard = keyboards.create_confirm_delete_keyboard(prompt_id)
            await query.edit_message_text(
                "Are you sure you want to delete this shared prompt?",
                reply_markup=keyboard
            )
        except (ValueError, IndexError):
            logger.warning(f"Invalid callback data format for delete: {data}")

    elif data.startswith("confirm_delete_prompt:"):
        try:
            prompt_id = int(data.split(":")[1])
            prompt_service: PromptService = context.bot_data["prompt_service"]
            # We call the service method, which calls the correct crud method
            deleted = prompt_service.delete_shared_prompt(user_id=user_id, prompt_id=prompt_id)
            if deleted:
                await query.answer("Shared prompt deleted.", show_alert=True)
            else:
                await query.answer("Could not delete prompt.", show_alert=True)
            await show_prompt_management_menu(update, context)
        except (ValueError, IndexError):
            logger.warning(f"Invalid callback data format for confirm_delete: {data}")

    elif data == "cancel_delete":
        await show_prompt_management_menu(update, context)
