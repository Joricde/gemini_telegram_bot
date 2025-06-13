# bot/services/prompt_service.py
from sqlalchemy.orm import Session
from typing import List, Optional, TypedDict, Literal

from bot.database import crud
from bot.database import models
from bot.core.config import settings
from bot.core.logging import logger


# This unified structure is great! We'll keep it.
class UnifiedPrompt(TypedDict):
    key: str  # A unique key like 'yaml:default' or 'db:123'
    title: str
    source: Literal["yaml", "db"]


class PromptService:
    """Service layer for handling logic related to all available prompts."""

    def __init__(self, db: Session):
        self.db = db

    def create_new_prompt(self, user_id: int, title: str, text: str) -> Optional[models.Prompt]:
        """Creates a new shared prompt in the database."""
        try:
            # This correctly calls the working CRUD function
            prompt = crud.create_user_prompt(db=self.db, user_id=user_id, title=title, text=text)
            logger.info(f"Successfully created shared prompt '{title}' for user {user_id}.")
            return prompt
        except Exception as e:
            logger.error(f"Error creating prompt for user {user_id}: {e}", exc_info=True)
            self.db.rollback()
            return None

    def get_available_prompts(self) -> List[UnifiedPrompt]:
        """
        Gets a combined list of all available prompts from YAML and the database.
        This list is the same for all users.
        """
        unified_list: List[UnifiedPrompt] = []

        # 1. Add public prompts from prompts.yml
        for key, value in settings.prompts.items():
            unified_list.append({
                "key": f"yaml:{key}",
                "title": f"[Public] {value.get('title', key)}",
                "source": "yaml"
            })

        # 2. Add shared prompts from the database (FIXED TYPO)
        db_prompts = crud.get_all_db_prompts(db=self.db)
        for prompt in db_prompts:
            unified_list.append({
                "key": f"db:{prompt.id}",
                "title": f"[Shared] {prompt.title}",
                "source": "db"
            })

        return unified_list

    def get_prompt_text_by_key(self, prompt_key: str) -> Optional[str]:
        """
        Resolves a prompt key (e.g., 'yaml:default', 'db:123') to its text content.
        """
        if not prompt_key or ':' not in prompt_key:
            prompt_key = "yaml:default" # Fallback to default

        try:
            source, key = prompt_key.split(":", 1)
            if source == "yaml":
                return settings.prompts.get(key, {}).get("prompt")
            elif source == "db":
                prompt_id = int(key)
                prompt_obj = crud.get_db_prompt_by_id(db=self.db, prompt_id=prompt_id)
                return prompt_obj.prompt_text if prompt_obj else None
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid prompt key format: {prompt_key}. Error: {e}")
            return None # Return None if key is invalid

    def delete_shared_prompt(self, user_id: int, prompt_id: int) -> bool:
        """Deletes a shared prompt from the database."""
        return crud.delete_prompt(db=self.db, user_id=user_id, prompt_id=prompt_id)