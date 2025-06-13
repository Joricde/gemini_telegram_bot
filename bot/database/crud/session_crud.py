from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, Dict, Any, List
from .. import models
import datetime

def get_active_chat_session_state(db: Session, user_id: int, chat_id: int) -> Optional[models.ChatSessionState]:
    """
    Retrieves the currently active chat session for a user in a specific chat.
    """
    return db.query(models.ChatSessionState).filter(
        models.ChatSessionState.telegram_user_id == user_id,
        models.ChatSessionState.telegram_chat_id == chat_id,
        models.ChatSessionState.is_active == True
    ).first()

def archive_previous_active_sessions(db: Session, user_id: int, chat_id: int):
    """
    Sets all active sessions for a user in a chat to inactive.
    """
    db.query(models.ChatSessionState).filter(
        models.ChatSessionState.telegram_user_id == user_id,
        models.ChatSessionState.telegram_chat_id == chat_id,
        models.ChatSessionState.is_active == True
    ).update({"is_active": False})
    db.commit()


def create_new_chat_session(db: Session, user_id: int, chat_id: int, prompt_id: int,
                            initial_history: Optional[List[Dict[str, Any]]] = None) -> models.ChatSessionState:
    """
    Archives old sessions and creates a new active chat session.
    """
    # 1. Archive previous sessions for the user in the chat
    archive_previous_active_sessions(db, user_id, chat_id)

    # 2. Create a new session state
    new_session = models.ChatSessionState(
        telegram_user_id=user_id,
        telegram_chat_id=chat_id,
        prompt_id=prompt_id,
        is_active=True,
        chat_history=initial_history or [],
        last_interaction_at=datetime.datetime.utcnow()
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


def update_chat_history(db: Session, session_id: int, new_history: List[Dict[str, Any]]):
    """
    Updates the chat history for a specific session and touches the last_interaction_at timestamp.
    """
    db.query(models.ChatSessionState).filter(models.ChatSessionState.id == session_id).update({
        "chat_history": new_history,
        "last_interaction_at": datetime.datetime.utcnow()
    })
    db.commit()