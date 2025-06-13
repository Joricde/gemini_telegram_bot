# bot/telegram/keyboards.py
from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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


def create_prompt_list_keyboard(prompts: List[models.Prompt]) -> InlineKeyboardMarkup:
    """
    Creates a keyboard to display a list of user-defined prompts.
    Each row has the prompt title and a delete button.
    """
    keyboard = []
    for prompt in prompts:
        # Add a checkmark if the prompt is active
        button_text = f"✅ {prompt.title}" if prompt.is_active else prompt.title

        # We create a row with two buttons: one to select, one to delete
        row = [
            InlineKeyboardButton(button_text, callback_data=f"select_prompt:{prompt.id}"),
            InlineKeyboardButton("❌", callback_data=f"delete_prompt:{prompt.id}"),
        ]
        keyboard.append(row)

    # Add navigation buttons at the bottom
    keyboard.append([
        InlineKeyboardButton("＋ Add New Prompt", callback_data="add_new_prompt"),
        InlineKeyboardButton("« Back to Main Menu", callback_data="start_menu"),
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
