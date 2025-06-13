# bot/database/crud/session_crud.py
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import datetime
from datetime import timezone

from .. import models
from ...core.logging import logger


def get_session(db: Session, chat_id: int) -> Optional[models.ChatSessionState]:
    """Retrieves a chat session by its chat_id."""
    return db.query(models.ChatSessionState).filter(models.ChatSessionState.chat_id == chat_id).first()


def create_session(db: Session, chat_id: int) -> models.ChatSessionState:
    """Creates a new, empty chat session."""
    logger.info(f"Creating new chat session for chat_id: {chat_id}")
    db_session = models.ChatSessionState(
        chat_id=chat_id,
        history=[],  # Start with an empty history
        active_prompt_key='default',
        messages_since_last_reply=0
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


def get_or_create_session(db: Session, chat_id: int) -> models.ChatSessionState:
    """
    Retrieves a chat session by its chat_id, or creates a new one if it doesn't exist.
    """
    db_session = get_session(db, chat_id)
    if db_session:
        # Also update the last interaction time whenever a session is fetched
        db_session.last_interaction_at = datetime.datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_session)
        return db_session

    return create_session(db, chat_id)


def update_session(db: Session, chat_id: int, new_history: List[Dict[str, Any]],
                   messages_since_reply: Optional[int] = None) -> Optional[models.ChatSessionState]:
    """
    Updates a session's history and other state variables.
    """
    db_session = get_session(db, chat_id)
    if db_session:
        db_session.history = new_history
        db_session.last_interaction_at = datetime.datetime.now(timezone.utc)
        if messages_since_reply is not None:
            db_session.messages_since_last_reply = messages_since_reply

        db.commit()
        db.refresh(db_session)
        return db_session
    else:
        logger.warning(f"Attempted to update a non-existent session for chat_id: {chat_id}")
        return None


def reset_session(db: Session, chat_id: int) -> Optional[models.ChatSessionState]:
    """
    Resets a session's history and counters, effectively starting it fresh.
    """
    db_session = get_session(db, chat_id)
    if db_session:
        logger.info(f"Resetting session for chat_id: {chat_id}")
        db_session.history = []
        db_session.messages_since_last_reply = 0
        db_session.last_interaction_at = datetime.datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_session)
        return db_session
    return None
