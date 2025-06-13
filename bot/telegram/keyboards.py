# bot/telegram/keyboards.py
from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.services.prompt_service import UnifiedPrompt
from bot.database import models


def create_start_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Creates the main menu keyboard shown with the /start command.
    """
    keyboard = [
        [InlineKeyboardButton("Change Persona / View Prompts", callback_data="manage_prompts")],
        [InlineKeyboardButton("Add New Prompt", callback_data="add_new_prompt")],
        [
            InlineKeyboardButton("Clear History", callback_data="clear_history"),
            InlineKeyboardButton("Help", callback_data="help_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def create_prompt_list_keyboard(prompts: List[UnifiedPrompt], active_key: str) -> InlineKeyboardMarkup:
    """
    Creates a keyboard to display a list of all available prompts.

    Args:
        prompts: A list of UnifiedPrompt objects from PromptService.
        active_key: The key of the currently active prompt for this session.
    """
    keyboard = []
    for prompt in prompts:
        # Check if the current prompt's key matches the session's active key
        is_active = prompt["key"] == active_key
        button_text = f"✅ {prompt['title']}" if is_active else prompt['title']

        # The callback data must be the unique key
        callback_data_select = f"select_prompt:{prompt['key']}"

        row = [InlineKeyboardButton(button_text, callback_data=callback_data_select)]

        # Only allow deleting prompts from the database (source: 'db')
        if prompt['source'] == 'db':
            prompt_id = prompt['key'].split(':')[1]
            callback_data_delete = f"delete_prompt:{prompt_id}"
            row.append(InlineKeyboardButton("❌", callback_data=callback_data_delete))

        keyboard.append(row)

    # Add navigation buttons at the bottom
    keyboard.append([
        InlineKeyboardButton("＋ Add New", callback_data="add_new_prompt"),
        InlineKeyboardButton("« Back", callback_data="start_menu"),
    ])

    return InlineKeyboardMarkup(keyboard)


def create_confirm_delete_keyboard(prompt_id: int) -> InlineKeyboardMarkup:
    """
    Creates a confirmation keyboard for deleting a prompt.

    Args:
        prompt_id: The ID of the prompt to be deleted.
    """
    keyboard = [
        [
            InlineKeyboardButton("Yes, Delete It", callback_data=f"confirm_delete_prompt:{prompt_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"cancel_delete_prompt:{prompt_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
