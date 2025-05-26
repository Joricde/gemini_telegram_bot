# gemini-telegram-bot/bot/database/crud.py

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc # For ordering by last_interaction_at
from . import models  # 从同目录下的 models.py 导入模型
from bot.utils import log  # 导入日志记录器
import json  # 用于序列化/反序列化 history
from typing import List, Optional # For type hinting

# --- User CRUD ---
def get_user(db: Session, user_id: str) -> models.User | None:
    return db.query(models.User).filter(models.User.user_id == user_id).first()


def create_user(db: Session, user_id: str, username: str | None = None, first_name: str | None = None,
                last_name: str | None = None) -> models.User:
    db_user = models.User(
        user_id=str(user_id),  # 确保是字符串
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    db.add(db_user)
    try:
        db.commit()
        db.refresh(db_user)
        log.info(f"User created: {user_id}")
    except IntegrityError:
        db.rollback()
        log.warning(f"User {user_id} already exists or other integrity error when creating user.")
        # Query again in case of race condition or if already exists
        db_user = get_user(db, user_id)
        if not db_user: # Should not happen if integrity error was due to existing user
            log.error(f"User {user_id} not found after presumed IntegrityError on creation.")
            # Potentially re-raise or handle as a more critical error
            raise
    return db_user


def get_or_create_user(db: Session, user_id: str, username: str | None = None, first_name: str | None = None,
                       last_name: str | None = None) -> models.User:
    db_user = get_user(db, user_id=str(user_id))
    if db_user:
        updated = False
        if username is not None and db_user.username != username:
            db_user.username = username
            updated = True
        if first_name is not None and db_user.first_name != first_name:
            db_user.first_name = first_name
            updated = True
        if last_name is not None and db_user.last_name != last_name: # Added last_name update
            db_user.last_name = last_name
            updated = True
        if updated:
            try:
                db.commit()
                db.refresh(db_user)
                log.info(f"User info updated for {user_id}")
            except Exception as e:
                db.rollback()
                log.error(f"Error updating user {user_id}: {e}")
        return db_user
    return create_user(db, user_id=str(user_id), username=username, first_name=first_name, last_name=last_name)


# --- Prompt CRUD ---
def get_prompt_by_id(db: Session, prompt_id: int) -> models.Prompt | None:
    return db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()


def get_prompt_by_name(db: Session, name: str) -> models.Prompt | None:
    return db.query(models.Prompt).filter(models.Prompt.name == name).first()


def get_prompts_by_user(db: Session, user_id: str, skip: int = 0, limit: int = 100) -> list[models.Prompt]:
    return db.query(models.Prompt).filter(models.Prompt.creator_user_id == user_id).offset(skip).limit(limit).all()


def get_system_default_prompts(db: Session, skip: int = 0, limit: int = 100) -> list[models.Prompt]:
    return db.query(models.Prompt).filter(models.Prompt.is_system_default == True).offset(skip).limit(limit).all()


def create_prompt(db: Session, name: str, system_instruction: str, creator_user_id: str | None = None,
                  description: str | None = None, temperature: float | None = None, top_p: float | None = None,
                  top_k: int | None = None, max_output_tokens: int | None = None,
                  base_model_override: str | None = None, is_system_default: bool = False) -> models.Prompt | None:
    db_prompt = models.Prompt(
        name=name,
        system_instruction=system_instruction,
        creator_user_id=creator_user_id,
        description=description,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        max_output_tokens=max_output_tokens,
        base_model_override=base_model_override,
        is_system_default=is_system_default
    )
    db.add(db_prompt)
    try:
        db.commit()
        db.refresh(db_prompt)
        log.info(f"Prompt created: {name}")
        return db_prompt
    except IntegrityError as e:
        db.rollback()
        log.error(f"Could not create prompt '{name}'. Integrity error (e.g. name not unique?): {e}")
        return None
    except Exception as e: # Catch other potential errors
        db.rollback()
        log.error(f"Unexpected error creating prompt '{name}': {e}", exc_info=True)
        return None


# --- ChatSessionState CRUD (Modified) ---

def get_active_chat_session_state(db: Session, telegram_chat_id: str,
                                  telegram_user_id: str | None = None) -> models.ChatSessionState | None:
    """
    Retrieves the single active chat session for a given telegram_chat_id and telegram_user_id.
    """
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id) if telegram_user_id else None

    query = db.query(models.ChatSessionState).filter(
        models.ChatSessionState.telegram_chat_id == telegram_chat_id_str,
        models.ChatSessionState.is_active == True
    )
    if telegram_user_id_str:
        query = query.filter(models.ChatSessionState.telegram_user_id == telegram_user_id_str)
    else:
        query = query.filter(models.ChatSessionState.telegram_user_id.is_(None))

    # In case of data inconsistency where multiple active sessions might exist,
    # order by last_interaction_at descending and pick the latest one.
    active_sessions = query.order_by(desc(models.ChatSessionState.last_interaction_at)).all()

    if not active_sessions:
        return None
    if len(active_sessions) > 1:
        log.warning(
            f"Multiple active sessions found for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}. "
            f"Returning the most recent one. Found IDs: {[s.id for s in active_sessions]}"
        )
        # Deactivate older ones to correct data inconsistency
        for i in range(1, len(active_sessions)):
            active_sessions[i].is_active = False
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            log.error(f"Error deactivating redundant active sessions: {e}", exc_info=True)

    return active_sessions[0]


def archive_previous_active_sessions(db: Session, telegram_chat_id: str,
                                     telegram_user_id: str | None = None) -> None:
    """
    Sets is_active=False for all currently active sessions for the given chat_id and user_id.
    """
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id) if telegram_user_id else None

    query = db.query(models.ChatSessionState).filter(
        models.ChatSessionState.telegram_chat_id == telegram_chat_id_str,
        models.ChatSessionState.is_active == True
    )
    if telegram_user_id_str:
        query = query.filter(models.ChatSessionState.telegram_user_id == telegram_user_id_str)
    else:
        query = query.filter(models.ChatSessionState.telegram_user_id.is_(None))

    sessions_to_archive = query.all()
    if not sessions_to_archive:
        return # No active sessions to archive

    for session in sessions_to_archive:
        session.is_active = False
        log.info(f"Archiving session ID {session.id} for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"Error archiving sessions for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}: {e}", exc_info=True)
        raise # Re-raise to indicate failure


def create_new_chat_session(
        db: Session,
        telegram_chat_id: str,
        active_prompt_id: int,
        current_base_model: str,
        telegram_user_id: str | None = None
) -> models.ChatSessionState:
    """
    Archives any existing active sessions for the user/chat and creates a new active session.
    """
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id) if telegram_user_id else None

    # Archive previous active sessions for this chat/user combination
    archive_previous_active_sessions(db, telegram_chat_id_str, telegram_user_id_str)

    # Create the new session
    new_session = models.ChatSessionState(
        telegram_chat_id=telegram_chat_id_str,
        telegram_user_id=telegram_user_id_str,
        active_prompt_id=active_prompt_id,
        current_base_model=current_base_model,
        gemini_chat_history=json.dumps([]),  # Start with empty history
        is_active=True
        # last_interaction_at and created_at will have server_default
    )
    db.add(new_session)
    try:
        db.commit()
        db.refresh(new_session)
        log.info(f"Created new active session ID {new_session.id} for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}, prompt_id {active_prompt_id}")
        return new_session
    except Exception as e:
        db.rollback()
        log.error(
            f"Error creating new session for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}: {e}",
            exc_info=True)
        raise


def update_chat_history(
    db: Session,
    session_id: int,
    new_gemini_chat_history: Optional[List[dict]] # Expecting list of serializable dicts
) -> models.ChatSessionState | None:
    """
    Updates the chat history of a specific, active chat session.
    The last_interaction_at field is expected to be updated by the database's onupdate trigger.
    """
    session_to_update = db.query(models.ChatSessionState).filter(
        models.ChatSessionState.id == session_id,
        models.ChatSessionState.is_active == True # Only update active sessions this way
    ).first()

    if not session_to_update:
        log.warning(f"Attempted to update history for non-existent or inactive session ID {session_id}.")
        return None

    history_json = None
    if new_gemini_chat_history:
        try:
            history_json = json.dumps(new_gemini_chat_history)
        except Exception as e:
            log.error(f"Error serializing chat history for session ID {session_id}: {e}", exc_info=True)
            # Depending on policy, either don't update history or raise error
            return None # Or raise

    session_to_update.gemini_chat_history = history_json
    # session_to_update.last_interaction_at = func.now() # if not using onupdate in model for some reason

    try:
        db.commit()
        db.refresh(session_to_update)
        log.debug(f"Updated history for active session ID {session_id}. History length: {len(new_gemini_chat_history or [])}")
        return session_to_update
    except Exception as e:
        db.rollback()
        log.error(f"Error committing history update for session ID {session_id}: {e}", exc_info=True)
        raise


def get_deserialized_chat_history(db_session_state: models.ChatSessionState) -> list | None:
    if db_session_state and db_session_state.gemini_chat_history:
        try:
            return json.loads(db_session_state.gemini_chat_history)
        except json.JSONDecodeError as e:
            log.error(f"Error deserializing chat history for session id {db_session_state.id}: {e}")
            return None
    return [] # Return empty list if no history, to simplify calling code


# --- GroupSetting CRUD ---
def get_group_setting(db: Session, group_id: str) -> models.GroupSetting | None:
    return db.query(models.GroupSetting).filter(models.GroupSetting.group_id == str(group_id)).first()


def create_or_update_group_setting(db: Session, group_id: str, default_mode: str | None = None,
                                   shared_mode_prompt_id: int | None = None,
                                   random_reply_enabled: bool | None = None) -> models.GroupSetting:
    group_id_str = str(group_id)
    db_group_setting = get_group_setting(db, group_id_str)

    if db_group_setting:
        if default_mode is not None:
            db_group_setting.default_mode = default_mode
        # Allow unsetting shared_mode_prompt_id by passing None explicitly
        if shared_mode_prompt_id is not None or ('shared_mode_prompt_id' in locals() and shared_mode_prompt_id is None):
            db_group_setting.shared_mode_prompt_id = shared_mode_prompt_id
        if random_reply_enabled is not None:
            db_group_setting.random_reply_enabled = random_reply_enabled
        log.info(f"Updating group setting for {group_id_str}")
    else:
        db_group_setting = models.GroupSetting(group_id=group_id_str)
        if default_mode is not None: db_group_setting.default_mode = default_mode
        if shared_mode_prompt_id is not None: db_group_setting.shared_mode_prompt_id = shared_mode_prompt_id
        if random_reply_enabled is not None: db_group_setting.random_reply_enabled = random_reply_enabled
        db.add(db_group_setting)
        log.info(f"Creating group setting for {group_id_str}")

    try:
        db.commit()
        db.refresh(db_group_setting)
    except Exception as e:
        db.rollback()
        log.error(f"Error committing group setting for {group_id_str}: {e}")
        raise

    return db_group_setting

# --- GroupMessageCache CRUD ---
# (Keep existing functions or add as needed for Phase Five)
# Example:
# def add_message_to_cache(db: Session, group_id: str, message_id: str, user_id: Optional[str], username: Optional[str], text: Optional[str]) -> models.GroupMessageCache:
#     # Implementation ...
#     pass