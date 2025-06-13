from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from .. import models
import datetime

def create_or_update_group_setting(db: Session, chat_id: int, **kwargs) -> models.GroupSetting:
    """
    Creates or updates settings for a specific group chat.
    """
    setting = db.query(models.GroupSetting).filter(models.GroupSetting.telegram_chat_id == chat_id).first()
    if setting:
        for key, value in kwargs.items():
            setattr(setting, key, value)
    else:
        setting = models.GroupSetting(telegram_chat_id=chat_id, **kwargs)
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def add_message_to_cache(db: Session, user_id: int, chat_id: int, message_text: str):
    """
    Adds a message to the group message cache.
    """
    new_message = models.GroupMessageCache(
        telegram_user_id=user_id,
        telegram_chat_id=chat_id,
        message_text=message_text,
        timestamp=datetime.datetime.utcnow()
    )
    db.add(new_message)
    db.commit()


def get_recent_messages_from_cache(db: Session, chat_id: int, limit: int = 10) -> List[models.GroupMessageCache]:
    """
    Retrieves the most recent messages from a group's cache.
    """
    return db.query(models.GroupMessageCache).filter(
        models.GroupMessageCache.telegram_chat_id == chat_id
    ).order_by(desc(models.GroupMessageCache.timestamp)).limit(limit).all()