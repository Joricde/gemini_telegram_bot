# bot/database/crud/user_crud.py
from sqlalchemy.orm import Session
from typing import Optional
import telegram

from .. import models
from ...core.logging import logger


def get_user(db: Session, user_id: int) -> Optional[models.User]:
    """Retrieves a single user by their Telegram ID."""
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_or_create_user(db: Session, user_data: telegram.User) -> models.User:
    """
    Retrieves a user by their Telegram ID, or creates them if they don't exist.
    Also updates the user's information if it has changed.
    """
    db_user = get_user(db, user_data.id)
    if db_user:
        # User exists, check for updates to name/username
        if (db_user.username != user_data.username or
                db_user.first_name != user_data.first_name ):
            db_user.username = user_data.username
            db_user.first_name = user_data.first_name
            db.commit()
            db.refresh(db_user)
        return db_user

    # User doesn't exist, create a new one
    logger.info(f"Creating new user: {user_data.username} (ID: {user_data.id})")
    new_user = models.User(
        id=user_data.id,
        username=user_data.username,
        first_name=user_data.first_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
