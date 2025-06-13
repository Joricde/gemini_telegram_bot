from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models

def create_user_prompt(db: Session, user_id: int, name: str, instruction: str) -> models.Prompt:
    """
    Creates a new private prompt for a user.
    """
    new_prompt = models.Prompt(
        user_id=user_id,
        name=name,
        instruction=instruction,
        prompt_type=models.PromptType.PRIVATE
    )
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)
    return new_prompt

def get_user_prompts(db: Session, user_id: int) -> List[models.Prompt]:
    """
    Retrieves all private prompts for a specific user.
    """
    return db.query(models.Prompt).filter(
        models.Prompt.user_id == user_id,
        models.Prompt.prompt_type == models.PromptType.PRIVATE
    ).all()

def get_system_prompts(db: Session) -> List[models.Prompt]:
    """
    Retrieves all system-level prompts.
    """
    return db.query(models.Prompt).filter(models.Prompt.prompt_type == models.PromptType.SYSTEM).all()

def get_prompt_by_id_and_user(db: Session, prompt_id: int, user_id: int) -> Optional[models.Prompt]:
    """
    Retrieves a specific prompt by its ID, ensuring it belongs to the user.
    """
    return db.query(models.Prompt).filter(
        models.Prompt.id == prompt_id,
        models.Prompt.user_id == user_id
    ).first()

def delete_prompt_by_id_and_user(db: Session, prompt_id: int, user_id: int) -> bool:
    """
    Deletes a prompt by its ID, ensuring it belongs to the user.
    Returns True if deletion was successful, False otherwise.
    """
    prompt_to_delete = get_prompt_by_id_and_user(db, prompt_id, user_id)
    if prompt_to_delete:
        db.delete(prompt_to_delete)
        db.commit()
        return True
    return False

def update_prompt_instruction(db: Session, prompt_id: int, user_id: int, new_instruction: str) -> Optional[models.Prompt]:
    """
    Updates the instruction of a specific prompt, ensuring it belongs to the user.
    """
    prompt_to_update = get_prompt_by_id_and_user(db, prompt_id, user_id)
    if prompt_to_update:
        prompt_to_update.instruction = new_instruction
        db.commit()
        db.refresh(prompt_to_update)
        return prompt_to_update
    return None