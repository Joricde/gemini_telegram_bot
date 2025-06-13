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
    return db.query(models.Prompt).order_by(models.Prompt.id).all() # Added order_by for consistency

def get_db_prompt_by_id(db: Session, prompt_id: int) -> Optional[models.Prompt]:
    """Retrieves a single prompt by its primary key ID."""
    return db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()

# 关键：删除这个错误的函数
# def set_active_prompt_for_user(...)

def delete_prompt(db: Session, user_id: int, prompt_id: int) -> bool:
    """
    Deletes a prompt. We check ownership before deleting.
    We still take user_id for logging and ownership check.
    """
    db_prompt = db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()
    if db_prompt:
        # Optional: You might want to allow only creators or admins to delete.
        # For now, we'll allow anyone as per the shared-use spirit.
        db.delete(db_prompt)
        db.commit()
        logger.info(f"User (ID: {user_id}) deleted prompt (ID: {prompt_id})")
        return True
    return False

# This function name is misleading but might be used elsewhere. We'll fix calls to it later.
# For now, it just gets all prompts.
def get_user_prompts(db: Session, user_id: int) -> List[models.Prompt]:
    """DEPRECATED - Use get_all_db_prompts. Retrieves all shared prompts."""
    logger.warning("Called deprecated function get_user_prompts. Use get_all_db_prompts instead.")
    return get_all_db_prompts(db)
