# bot/services/prompt_service.py
from sqlalchemy.orm import Session
from typing import List, Optional, TypedDict, Literal

from bot.database import crud
from bot.database import models
from bot.core.config import settings
from bot.core.logging import logger


# Define a unified structure for all prompts to be sent to the UI
class UnifiedPrompt(TypedDict):
    id: str  # Can be a DB id (int as str) or a YAML key (str)
    title: str
    is_active: bool
    source: Literal["db", "yaml"]


class PromptService:
    """Service layer for handling logic related to all available prompts."""

    def __init__(self, db: Session):
        self.db = db

    def create_new_prompt(self, user_id: int, title: str, text: str) -> Optional[models.Prompt]:
        """Creates a new shared prompt in the database."""
        try:
            prompt = crud.create_user_prompt(db=self.db, user_id=user_id, title=title, text=text)
            logger.info(f"Successfully created shared prompt '{title}' for user {user_id}.")
            return prompt
        except Exception as e:
            logger.error(f"Error creating prompt for user {user_id}: {e}", exc_info=True)
            self.db.rollback()
            return None

    def get_available_prompts(self, active_prompt_key: str) -> List[UnifiedPrompt]:
        """
        Gets a combined list of all available prompts from YAML and the database.

        Args:
            active_prompt_key: The key of the currently active prompt for the session
                               (e.g., 'yaml:default', 'db:123').

        Returns:
            A unified list of prompts for display.
        """
        unified_list: List[UnifiedPrompt] = []

        # 1. Add public prompts from prompts.yml
        for key, value in settings.prompts.items():
            unified_list.append({
                "id": key,
                "title": f"[Public] {value['title']}",
                "is_active": active_prompt_key == f"yaml:{key}",
                "source": "yaml"
            })

        # 2. Add shared prompts from the database
        db_prompts = crud.higet_all_db_prompts(db=self.db)
        for prompt in db_prompts:
            unified_list.append({
                "id": str(prompt.id),
                "title": f"[Shared] {prompt.title}",
                "is_active": active_prompt_key == f"db:{prompt.id}",
                "source": "db"
            })

        return unified_list

    def delete_shared_prompt(self, user_id: int, prompt_id: int) -> bool:
        """Deletes a shared prompt from the database."""
        # user_id is passed for logging purposes
        return crud.delete_prompt(db=self.db, user_id=user_id, prompt_id=prompt_id)
