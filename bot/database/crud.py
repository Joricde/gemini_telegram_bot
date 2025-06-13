# gemini-telegram-bot/bot/database/crud.py
import datetime

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc, and_  # For ordering and combined filters
from . import models  # From bot.database.models
from .models import PromptType  # Import the Enum
from bot.utils import log
import json
from typing import List, Optional


# --- User CRUD ---
def get_user(db: Session, user_id: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.user_id == str(user_id)).first()


def create_user(db: Session, user_id: str, username: Optional[str] = None,
                first_name: Optional[str] = None, last_name: Optional[str] = None) -> models.User:
    db_user = models.User(
        user_id=str(user_id),
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
        log.warning(f"User {user_id} already exists or other integrity error. Returning existing.")
        # Query again to ensure we return the object, even if it was a race condition.
        existing_user = get_user(db, str(user_id))
        if existing_user:
            return existing_user
        else:
            # This case should ideally not be reached if IntegrityError was due to PK violation
            log.error(f"User {user_id} not found after IntegrityError on creation and subsequent get.")
            raise  # Or handle as a more severe error
    return db_user


def get_or_create_user(db: Session, user_id: str, username: Optional[str] = None,
                       first_name: Optional[str] = None, last_name: Optional[str] = None) -> models.User:
    user_id_str = str(user_id)
    db_user = get_user(db, user_id_str)
    if db_user:
        updated = False
        if username is not None and db_user.username != username:
            db_user.username = username
            updated = True
        if first_name is not None and db_user.first_name != first_name:
            db_user.first_name = first_name
            updated = True
        if last_name is not None and db_user.last_name != last_name:
            db_user.last_name = last_name
            updated = True

        if updated:
            try:
                # db_user.updated_at = datetime.datetime.now(datetime.timezone.utc) # Handled by onupdate in model
                db.commit()
                db.refresh(db_user)
                log.info(f"User info updated for {user_id_str}")
            except Exception as e:
                db.rollback()
                log.error(f"Error updating user {user_id_str}: {e}", exc_info=True)
                # Potentially re-fetch the user to ensure the returned object is in a valid state
                db_user = get_user(db, user_id_str)
                if not db_user:  # Should not happen
                    log.critical(f"User {user_id_str} lost after failed update attempt.")
                    raise
        return db_user
    return create_user(db, user_id_str, username=username, first_name=first_name, last_name=last_name)


# --- Prompt CRUD ---
def get_prompt_by_id(db: Session, prompt_id: int) -> Optional[models.Prompt]:
    return db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()


def get_prompt_by_id_and_user(db: Session, prompt_id: int, user_id: str) -> Optional[models.Prompt]:
    """Fetches a prompt only if it belongs to the specified user or is a system default prompt."""
    user_id_str = str(user_id)
    prompt = db.query(models.Prompt).filter(models.Prompt.id == prompt_id).first()
    if prompt:
        if prompt.is_system_default or prompt.creator_user_id == user_id_str:
            return prompt
        # If prompt exists but doesn't belong to user and isn't system default
        log.warning(
            f"User {user_id_str} attempted to access prompt ID {prompt_id} not owned by them and not system default.")
        return None
    return None


def get_prompt_by_name_and_user(db: Session, name: str, user_id: str, prompt_type: PromptType) -> Optional[
    models.Prompt]:
    """
    Fetches a prompt by its name, creator_user_id, and prompt_type.
    Used to check if a user already has a specific prompt.
    """
    user_id_str = str(user_id)
    return db.query(models.Prompt).filter(
        models.Prompt.name == name,
        models.Prompt.creator_user_id == user_id_str,
        models.Prompt.prompt_type == prompt_type
    ).first()


def get_system_prompt_by_name(db: Session, name: str) -> Optional[models.Prompt]:
    """Fetches a system default prompt by its name."""
    return db.query(models.Prompt).filter(
        models.Prompt.name == name,
        models.Prompt.is_system_default == True
    ).first()


def get_prompts_by_user_and_type(db: Session, user_id: str, prompt_type: PromptType,
                                 skip: int = 0, limit: int = 100) -> List[models.Prompt]:
    user_id_str = str(user_id)
    return db.query(models.Prompt).filter(
        models.Prompt.creator_user_id == user_id_str,
        models.Prompt.prompt_type == prompt_type
    ).order_by(models.Prompt.name).offset(skip).limit(limit).all()


def get_system_default_prompts(db: Session, prompt_type: Optional[PromptType] = None,
                               skip: int = 0, limit: int = 100) -> List[models.Prompt]:
    query = db.query(models.Prompt).filter(models.Prompt.is_system_default == True)
    if prompt_type:
        query = query.filter(models.Prompt.prompt_type == prompt_type)
    return query.order_by(models.Prompt.name).offset(skip).limit(limit).all()


def create_prompt(
        db: Session,
        name: str,
        system_instruction: str,
        prompt_type: PromptType,  # Now mandatory
        creator_user_id: Optional[str] = None,  # Nullable for system prompts
        description: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        base_model_override: Optional[str] = None,
        is_system_default: bool = False
) -> Optional[models.Prompt]:
    # For user-created prompts, check for name collision for the same type
    if not is_system_default and creator_user_id:
        existing_user_prompt = get_prompt_by_name_and_user(db, name, creator_user_id, prompt_type)
        if existing_user_prompt:
            log.warning(
                f"User {creator_user_id} tried to create prompt '{name}' of type '{prompt_type.value}' but it already exists.")
            return None  # Or raise an exception / return specific error

    db_prompt = models.Prompt(
        name=name,
        system_instruction=system_instruction,
        prompt_type=prompt_type,
        creator_user_id=str(creator_user_id) if creator_user_id else None,
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
        log.info(
            f"Prompt created: '{name}' (Type: {prompt_type.value}, System: {is_system_default}, User: {creator_user_id})")
        return db_prompt
    except IntegrityError as e:  # Handles other integrity issues like DB constraints not caught by app logic
        db.rollback()
        log.error(f"Could not create prompt '{name}'. Integrity error: {e}", exc_info=True)
        return None
    except Exception as e:
        db.rollback()
        log.error(f"Unexpected error creating prompt '{name}': {e}", exc_info=True)
        return None


def update_prompt_instruction(db: Session, prompt_id: int, new_system_instruction: str, user_id: str) -> Optional[
    models.Prompt]:
    """Updates the system_instruction of a user-owned prompt."""
    user_id_str = str(user_id)
    prompt_to_update = db.query(models.Prompt).filter(
        models.Prompt.id == prompt_id,
        models.Prompt.creator_user_id == user_id_str,
        models.Prompt.is_system_default == False  # Users cannot edit system prompts
    ).first()

    if not prompt_to_update:
        log.warning(f"User {user_id_str} attempted to update non-existent or non-owned/system prompt ID {prompt_id}.")
        return None

    prompt_to_update.system_instruction = new_system_instruction
    # prompt_to_update.updated_at = datetime.datetime.now(datetime.timezone.utc) # Handled by onupdate
    try:
        db.commit()
        db.refresh(prompt_to_update)
        log.info(f"User {user_id_str} updated instruction for prompt ID {prompt_id} ('{prompt_to_update.name}').")
        return prompt_to_update
    except Exception as e:
        db.rollback()
        log.error(f"Error updating prompt ID {prompt_id} for user {user_id_str}: {e}", exc_info=True)
        return None


def delete_prompt(db: Session, prompt_id: int, user_id: str) -> bool:
    """Deletes a user-owned prompt. Returns True if successful, False otherwise."""
    user_id_str = str(user_id)
    prompt_to_delete = db.query(models.Prompt).filter(
        models.Prompt.id == prompt_id,
        models.Prompt.creator_user_id == user_id_str,
        models.Prompt.is_system_default == False  # Users cannot delete system prompts
    ).first()

    if not prompt_to_delete:
        log.warning(f"User {user_id_str} attempted to delete non-existent or non-owned/system prompt ID {prompt_id}.")
        return False

    try:
        # Before deleting, check if this prompt is used in any GroupSetting
        # This is a soft check; ideally, foreign key constraints with ON DELETE SET NULL or RESTRICT would handle this at DB level.
        # For now, we'll just log a warning if it's in use. A more robust solution might prevent deletion or clear the FK.
        conflicting_group_settings = db.query(models.GroupSetting).filter(
            models.GroupSetting.shared_mode_role_prompt_id == prompt_id).count()
        if conflicting_group_settings > 0:
            log.warning(
                f"Prompt ID {prompt_id} ('{prompt_to_delete.name}') is currently used by {conflicting_group_settings} group(s) as shared_mode_role_prompt_id. Deleting anyway as per current logic.")
            # Add logic here if you want to prevent deletion or nullify FKs:
            # for gs in db.query(models.GroupSetting).filter(models.GroupSetting.shared_mode_role_prompt_id == prompt_id).all():
            #     gs.shared_mode_role_prompt_id = None

        # Also check ChatSessionState (though less likely to be a hard blocker for prompt deletion,
        # but active sessions might need to be reset or handled).
        # For simplicity, we are not handling cascading effects on ChatSessionState here, but it's a consideration.

        db.delete(prompt_to_delete)
        db.commit()
        log.info(f"User {user_id_str} deleted prompt ID {prompt_id} ('{prompt_to_delete.name}').")
        return True
    except Exception as e:
        db.rollback()
        log.error(f"Error deleting prompt ID {prompt_id} for user {user_id_str}: {e}", exc_info=True)
        return False


# (Continuing in bot/database/crud.py)
# Ensure these imports are at the top of the file if not already present
# import datetime # Already there from models.py if using models.PromptType
# from .models import PromptType # Already there
# from sqlalchemy import desc, and_ # Already there

# --- GroupSetting CRUD ---
def get_group_setting(db: Session, group_id: str) -> Optional[models.GroupSetting]:
    return db.query(models.GroupSetting).filter(models.GroupSetting.group_id == str(group_id)).first()


def create_or_update_group_setting(
        db: Session,
        group_id: str,
        current_mode: Optional[str] = None,
        shared_mode_role_prompt_id: Optional[int] = None,  # This is the ID of a 'group_role_payload' prompt
        random_reply_enabled: Optional[bool] = None
) -> models.GroupSetting:
    group_id_str = str(group_id)
    db_group_setting = get_group_setting(db, group_id_str)

    if db_group_setting:
        if current_mode is not None:
            db_group_setting.current_mode = current_mode
        if shared_mode_role_prompt_id is not None:  # Allows setting to None explicitly if 0 or other falsey value is passed for unsetting
            # Ensure the prompt ID exists and is of type GROUP_ROLE_PAYLOAD if not None
            if shared_mode_role_prompt_id:  # If a non-None, non-zero ID is provided
                prompt = get_prompt_by_id(db, shared_mode_role_prompt_id)
                if not prompt or prompt.prompt_type != PromptType.GROUP_ROLE_PAYLOAD:
                    log.warning(f"Attempted to set shared_mode_role_prompt_id to {shared_mode_role_prompt_id} "
                                f"for group {group_id_str}, but prompt is invalid or not a group role payload. Not updating.")
                    # Don't update if the prompt isn't valid for this purpose.
                else:
                    db_group_setting.shared_mode_role_prompt_id = shared_mode_role_prompt_id
            else:  # If shared_mode_role_prompt_id is explicitly None (or 0, which we treat as None here for FKs)
                db_group_setting.shared_mode_role_prompt_id = None

        if random_reply_enabled is not None:
            db_group_setting.random_reply_enabled = random_reply_enabled
        log.info(f"Updating group setting for {group_id_str}")
    else:
        # Ensure shared_mode_role_prompt_id is valid if provided for a new setting
        valid_initial_prompt_id = None
        if shared_mode_role_prompt_id:
            prompt = get_prompt_by_id(db, shared_mode_role_prompt_id)
            if prompt and prompt.prompt_type == PromptType.GROUP_ROLE_PAYLOAD:
                valid_initial_prompt_id = shared_mode_role_prompt_id
            else:
                log.warning(
                    f"Invalid shared_mode_role_prompt_id {shared_mode_role_prompt_id} for new group {group_id_str}. Setting to None.")

        db_group_setting = models.GroupSetting(
            group_id=group_id_str,
            current_mode=current_mode if current_mode is not None else "individual",  # Default
            shared_mode_role_prompt_id=valid_initial_prompt_id,
            random_reply_enabled=random_reply_enabled if random_reply_enabled is not None else True  # Default
        )
        db.add(db_group_setting)
        log.info(f"Creating group setting for {group_id_str}")

    try:
        db.commit()
        db.refresh(db_group_setting)
    except Exception as e:
        db.rollback()
        log.error(f"Error committing group setting for {group_id_str}: {e}", exc_info=True)
        # Re-fetch to ensure a consistent object state if it exists, or None
        existing_setting = get_group_setting(db, group_id_str)
        if not existing_setting and not db_group_setting.group_id:  # If creation failed rollback and object is transient
            raise
        return existing_setting or db_group_setting  # Return stale if refresh failed but existed
    return db_group_setting


# --- ChatSessionState CRUD ---
def get_active_chat_session_state(db: Session, telegram_chat_id: str,
                                  telegram_user_id: Optional[str] = None) -> Optional[models.ChatSessionState]:
    """Retrieves the single active chat session."""
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id) if telegram_user_id else None

    query = db.query(models.ChatSessionState).filter(
        models.ChatSessionState.telegram_chat_id == telegram_chat_id_str,
        models.ChatSessionState.is_active == True
    )
    if telegram_user_id_str:  # Specific user session (private chat or group-individual)
        query = query.filter(models.ChatSessionState.telegram_user_id == telegram_user_id_str)
    else:  # Shared group session
        query = query.filter(models.ChatSessionState.telegram_user_id.is_(None))

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
            # Proceed with returning the most recent one despite commit error for deactivation
    return active_sessions[0]


def archive_previous_active_sessions(db: Session, telegram_chat_id: str,
                                     telegram_user_id: Optional[str] = None) -> bool:
    """Sets is_active=False for all currently active sessions for the given chat_id and user_id. Returns True if any were archived."""
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
        return False

    archived_count = 0
    for session in sessions_to_archive:
        session.is_active = False
        log.info(
            f"Archiving session ID {session.id} for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}")
        archived_count += 1

    if archived_count > 0:
        try:
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            log.error(
                f"Error archiving sessions for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}: {e}",
                exc_info=True)
            # Depending on strictness, you might want to raise the error
            return False  # Indicate failure
    return False


def create_new_chat_session(
        db: Session,
        telegram_chat_id: str,
        active_prompt_id: int,  # This should be an ID of a 'private' type prompt
        current_base_model: str,
        telegram_user_id: Optional[str] = None,
        initial_history: Optional[List[dict]] = None  # Used if starting a session with predefined history
) -> Optional[models.ChatSessionState]:
    """Archives any existing active sessions and creates a new active session."""
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id) if telegram_user_id else None

    # Validate active_prompt_id refers to a 'private' type prompt,
    # as group shared sessions get their role from GroupSetting, not directly here.
    # This function is mainly for private chats or group-individual mode.
    prompt = get_prompt_by_id(db, active_prompt_id)
    if not prompt or prompt.prompt_type != PromptType.PRIVATE:
        # Allow system default private prompts too.
        if not (prompt and prompt.is_system_default and prompt.prompt_type == PromptType.PRIVATE):
            log.error(
                f"Cannot create chat session: active_prompt_id {active_prompt_id} is not a valid 'private' type prompt.")
            return None

    archive_previous_active_sessions(db, telegram_chat_id_str, telegram_user_id_str)

    history_json = json.dumps(initial_history if initial_history is not None else [])

    new_session = models.ChatSessionState(
        telegram_chat_id=telegram_chat_id_str,
        telegram_user_id=telegram_user_id_str,
        active_prompt_id=active_prompt_id,
        current_base_model=current_base_model,
        gemini_chat_history=history_json,
        is_active=True
    )
    db.add(new_session)
    try:
        db.commit()
        db.refresh(new_session)
        log.info(
            f"Created new active session ID {new_session.id} for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}, prompt_id {active_prompt_id}")
        return new_session
    except Exception as e:
        db.rollback()
        log.error(f"Error creating new session for chat_id {telegram_chat_id_str}, user_id {telegram_user_id_str}: {e}",
                  exc_info=True)
        return None  # Indicate failure


def update_chat_history(
        db: Session,
        session_id: int,
        new_gemini_chat_history: List[dict]  # Expecting list of serializable dicts
) -> Optional[models.ChatSessionState]:
    """Updates the chat history of a specific, active chat session."""
    session_to_update = db.query(models.ChatSessionState).filter(
        models.ChatSessionState.id == session_id,
        models.ChatSessionState.is_active == True
    ).first()

    if not session_to_update:
        log.warning(f"Attempted to update history for non-existent or inactive session ID {session_id}.")
        return None

    history_json = None
    try:
        history_json = json.dumps(new_gemini_chat_history)
    except TypeError as e:  # More specific exception for json.dumps
        log.error(f"Error serializing chat history for session ID {session_id}: {e}", exc_info=True)
        return None

    session_to_update.gemini_chat_history = history_json
    # last_interaction_at is handled by onupdate in the model
    try:
        db.commit()
        db.refresh(session_to_update)
        log.debug(f"Updated history for active session ID {session_id}. History items: {len(new_gemini_chat_history)}")
        return session_to_update
    except Exception as e:
        db.rollback()
        log.error(f"Error committing history update for session ID {session_id}: {e}", exc_info=True)
        return None  # Indicate failure


def get_deserialized_chat_history(session_state: models.ChatSessionState) -> List[dict]:
    """Safely deserializes chat history. Returns empty list on error or if no history."""
    if not session_state or not session_state.gemini_chat_history:
        return []
    try:
        history = json.loads(session_state.gemini_chat_history)
        return history if isinstance(history, list) else []
    except json.JSONDecodeError as e:
        log.error(f"Error deserializing chat history for session id {session_state.id}: {e}")
        return []


# --- GroupMessageCache CRUD ---
def add_message_to_cache(
        db: Session,
        group_id: str,
        message_id: str,
        timestamp: datetime.datetime,  # Make timestamp mandatory
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        text: Optional[str] = None
) -> Optional[models.GroupMessageCache]:
    # Optional: Check for duplicate message_id within the group to prevent issues, though DB constraint should handle it.
    # existing_msg = db.query(models.GroupMessageCache).filter_by(group_id=str(group_id), message_id=str(message_id)).first()
    # if existing_msg:
    #     log.warning(f"Message {message_id} from group {group_id} already in cache. Skipping.")
    #     return existing_msg

    db_message = models.GroupMessageCache(
        group_id=str(group_id),
        message_id=str(message_id),
        user_id=str(user_id) if user_id else None,
        username=username,
        text=text,
        timestamp=timestamp
    )
    db.add(db_message)
    try:
        db.commit()
        db.refresh(db_message)
        log.debug(f"Added message {message_id} from group {group_id} to cache.")
        return db_message
    except IntegrityError as e:  # Catch unique constraint violation if any
        db.rollback()
        log.warning(
            f"Integrity error adding message {message_id} from group {group_id} to cache (likely duplicate): {e}")
        return None  # Or fetch and return existing if that's desired behavior on duplicate
    except Exception as e:
        db.rollback()
        log.error(f"Error adding message to cache for group {group_id}: {e}", exc_info=True)
        return None


def get_recent_messages_from_cache(db: Session, group_id: str, limit: int = 10) -> List[models.GroupMessageCache]:
    """Retrieves the most recent messages from the cache for a given group."""
    return db.query(models.GroupMessageCache).filter(
        models.GroupMessageCache.group_id == str(group_id)
    ).order_by(desc(models.GroupMessageCache.timestamp)).limit(limit).all()
