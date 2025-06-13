# bot/database/crud/prompt_crud.py
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models
from ...core.logging import logger

def create_user_prompt(db: Session, user_id: int, title: str, text: str) -> models.Prompt:
    """Creates a new prompt, associating it with the user who created it."""
    logger.info(f"User (ID: {user_id}) creating new prompt with title: '{title}'")
    db_prompt = models.Prompt(user_id=user_id, title=title, prompt_text=text)
    db.add(db_prompt)
    db.commit()
    db.refresh(db_prompt)
    return db_prompt

def get_all_db_prompts(db: Session) -> List[models.Prompt]:
    """Retrieves all prompts from the database, as they are all shared."""
    return db.query(models.Prompt).all()

def get_db_prompt_by_id(db: Session, prompt_id: int) -> Optional[models.Prompt]:
    """Retrieves a single prompt by its primary key ID."""
    return db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()

def set_active_prompt_for_user(db: Session, user_id: int, prompt_id: int) -> Optional[models.Prompt]:
    """Sets a specific prompt as active for a user, deactivating all others."""
    # This function's logic remains the same, as the "active" status is per-user.
    try:
        db.query(models.Prompt).filter(
            models.Prompt.user_id == user_id,
            models.Prompt.is_active == True
        ).update({"is_active": False}, synchronize_session=False)

        db_prompt = db.query(models.Prompt).filter(models.Prompt.id == prompt_id, models.Prompt.user_id == user_id).first()
        if db_prompt:
            db_prompt.is_active = True
            db.commit()
            logger.info(f"User (ID: {user_id}) activated prompt (ID: {prompt_id})")
            return db_prompt
        else:
            db.rollback()
            return None
    except Exception as e:
        logger.error(f"Error setting active prompt: {e}")
        db.rollback()
        return None

def delete_prompt(db: Session, user_id: int, prompt_id: int) -> bool:
    """
    Deletes a prompt. In our shared model, any user can delete any prompt.
    We still take user_id for logging purposes.
    """
    db_prompt = db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()
    if db_prompt:
        db.delete(db_prompt)
        db.commit()
        logger.info(f"User (ID: {user_id}) deleted prompt (ID: {prompt_id})")
        return True
    return False
