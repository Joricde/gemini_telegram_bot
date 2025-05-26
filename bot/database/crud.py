# gemini-telegram-bot/bot/database/crud.py

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from . import models  # 从同目录下的 models.py 导入模型
from bot.utils import log  # 导入日志记录器
import json  # 用于序列化/反序列化 history


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
        log.warning(f"User {user_id} already exists or other integrity error.")
        # Query again in case of race condition or if already exists
        db_user = get_user(db, user_id)
    return db_user


def get_or_create_user(db: Session, user_id: str, username: str | None = None, first_name: str | None = None,
                       last_name: str | None = None) -> models.User:
    db_user = get_user(db, user_id=str(user_id))
    if db_user:
        # Optionally update user info if changed
        updated = False
        if username is not None and db_user.username != username:
            db_user.username = username
            updated = True
        if first_name is not None and db_user.first_name != first_name:
            db_user.first_name = first_name
            updated = True
        # Add more fields to update as needed
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
    # Ensure name is unique before creating
    if get_prompt_by_name(db, name):
        log.warning(f"Prompt with name '{name}' already exists. Cannot create duplicate.")
        return None # Or raise an exception / return a specific error code

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
        log.info(f"Prompt '{name}' created successfully by user {creator_user_id or 'System'}.")
        return db_prompt
    except IntegrityError as e:
        db.rollback()
        log.error(f"Could not create prompt '{name}'. Integrity error: {e}", exc_info=True)
        return None
    except Exception as e:
        db.rollback()
        log.error(f"An unexpected error occurred while creating prompt '{name}': {e}", exc_info=True)
        return None


# --- ChatSessionState CRUD ---
def get_chat_session_state(db: Session, telegram_chat_id: str,
                           telegram_user_id: str | None = None) -> models.ChatSessionState | None:
    query = db.query(models.ChatSessionState).filter(models.ChatSessionState.telegram_chat_id == str(telegram_chat_id))
    if telegram_user_id:
        query = query.filter(models.ChatSessionState.telegram_user_id == str(telegram_user_id))
    else:  # For shared group sessions or private chats where user_id might be same as chat_id
        query = query.filter(models.ChatSessionState.telegram_user_id.is_(None))  # Or a specific marker for shared
    return query.first()


def create_or_update_chat_session_state(
        db: Session,
        telegram_chat_id: str,
        active_prompt_id: int,
        current_base_model: str,
        telegram_user_id: str | None = None,
        gemini_chat_history: list | None = None  # Expecting a list of Gemini Message objects
) -> models.ChatSessionState:
    telegram_chat_id_str = str(telegram_chat_id)
    telegram_user_id_str = str(telegram_user_id) if telegram_user_id else None

    db_session_state = get_chat_session_state(db, telegram_chat_id_str, telegram_user_id_str)

    history_json = None
    if gemini_chat_history:
        # VERY IMPORTANT: Gemini Message objects are not directly JSON serializable.
        # You need a robust way to convert them to a storable format (e.g., dicts with 'role' and 'parts')
        # and back. For now, let's assume it's a list of dicts.
        try:
            history_json = json.dumps([msg if isinstance(msg, dict) else msg.to_dict() for msg in gemini_chat_history])
        except Exception as e:
            log.error(f"Error serializing chat history for {telegram_chat_id_str}/{telegram_user_id_str}: {e}")
            # Decide how to handle: store None, store partial, raise error?
            history_json = None  # Fallback to None

    if db_session_state:
        db_session_state.active_prompt_id = active_prompt_id
        db_session_state.current_base_model = current_base_model
        if history_json is not None:  # Only update if new history is valid
            db_session_state.gemini_chat_history = history_json
        # last_interaction_at will be updated automatically by onupdate
        log.debug(f"Updating session for {telegram_chat_id_str}/{telegram_user_id_str}")
    else:
        log.debug(f"Creating new session for {telegram_chat_id_str}/{telegram_user_id_str}")
        db_session_state = models.ChatSessionState(
            telegram_chat_id=telegram_chat_id_str,
            telegram_user_id=telegram_user_id_str,
            active_prompt_id=active_prompt_id,
            current_base_model=current_base_model,
            gemini_chat_history=history_json
        )
        db.add(db_session_state)

    try:
        db.commit()
        db.refresh(db_session_state)
    except Exception as e:
        db.rollback()
        log.error(f"Error committing session state for {telegram_chat_id_str}/{telegram_user_id_str}: {e}")
        raise  # Re-raise the exception after logging and rollback

    return db_session_state


def get_deserialized_chat_history(db_session_state: models.ChatSessionState) -> list | None:
    if db_session_state and db_session_state.gemini_chat_history:
        try:
            # This needs to be converted back to Gemini Message objects if your gemini_service expects that.
            # For now, it returns a list of dicts.
            return json.loads(db_session_state.gemini_chat_history)
        except json.JSONDecodeError as e:
            log.error(f"Error deserializing chat history for session id {db_session_state.id}: {e}")
            return None
    return None


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
        if shared_mode_prompt_id is not None:  # Allow unsetting with None
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
# Add functions for GroupMessageCache as needed, e.g.,
# def add_message_to_cache(...)
# def get_recent_messages_from_cache(...)
# def clear_old_messages_from_cache(...)