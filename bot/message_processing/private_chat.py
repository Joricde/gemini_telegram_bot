# bot/message_processing/private_chat.py

from sqlalchemy.orm import Session
from typing import Optional
import datetime  # Ensure datetime is imported

from bot.database import SessionLocal
from bot.database import models as db_models
from bot.database.crud import (
    get_or_create_user,
    get_active_chat_session_state,
    create_new_chat_session,
    update_chat_history,
    get_deserialized_chat_history,
    get_prompt_by_name,
    get_prompt_by_id
)
from bot.gemini_service import GeminiService
from bot.utils import log
from bot import APP_CONFIG, PROMPTS_CONFIG


async def handle_private_message(
        user_id: str,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        message_text: str,
        gemini_service: GeminiService
) -> Optional[str]:
    """
    Handles an incoming private message, interacts with Gemini, and updates the database,
    including session timeout logic and creation of new sessions.

    Returns:
        The text response from Gemini, or None if an error occurred.
    """
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        current_utc_time = datetime.datetime.now(datetime.timezone.utc)
        SESSION_TIMEOUT_SECONDS = 3600  # 1 hour

        db_user = get_or_create_user(db, user_id=user_id, username=username, first_name=first_name, last_name=last_name)
        if not db_user:
            log.error(f"Failed to get or create user {user_id} in private_chat.")
            return "抱歉，处理您的用户信息时出现问题。"

        active_session = get_active_chat_session_state(db, telegram_chat_id=user_id, telegram_user_id=user_id)

        session_to_use: Optional[db_models.ChatSessionState] = None

        if active_session:
            if active_session.last_interaction_at:
                # --- Fix for TypeError ---
                last_interaction_time = active_session.last_interaction_at
                if last_interaction_time.tzinfo is None or last_interaction_time.tzinfo.utcoffset(
                        last_interaction_time) is None:
                    log.debug(f"Session ID {active_session.id} last_interaction_at was naive. Localizing to UTC.")
                    last_interaction_time = last_interaction_time.replace(tzinfo=datetime.timezone.utc)
                # --- End Fix ---

                time_since_last_interaction = current_utc_time - last_interaction_time
                if time_since_last_interaction.total_seconds() > SESSION_TIMEOUT_SECONDS:
                    log.info(
                        f"Session ID {active_session.id} for user {user_id} timed out. Creating new session with same prompt.")
                    session_to_use = create_new_chat_session(
                        db=db,
                        telegram_chat_id=user_id,
                        telegram_user_id=user_id,
                        active_prompt_id=active_session.active_prompt_id,
                        current_base_model=active_session.current_base_model
                    )
                else:
                    session_to_use = active_session
            else:
                # This case (active session with no last_interaction_at) should be rare
                # as last_interaction_at has server_default and onupdate.
                log.warning(
                    f"Session ID {active_session.id} for user {user_id} has no last_interaction_at. Using session as is.")
                session_to_use = active_session

        if not session_to_use:
            log.info(
                f"No active session found for user {user_id} or previous timed out/was problematic. Creating new default session.")
            default_prompt_key = APP_CONFIG.get("default_bot_behavior", {}).get("default_prompt_key", "none_prompt")
            default_prompt_config = PROMPTS_CONFIG.get(default_prompt_key, {})
            default_prompt_name = default_prompt_config.get("name", default_prompt_key)

            active_prompt_object = get_prompt_by_name(db, name=default_prompt_name)
            if not active_prompt_object:
                active_prompt_object = get_prompt_by_name(db, name=default_prompt_key)

            if not active_prompt_object:
                log.error(
                    f"Default prompt '{default_prompt_name}' (or key '{default_prompt_key}') not found in DB for user {user_id}.")
                return "抱歉，我当前没有可用的默认角色设置。"

            default_base_model = active_prompt_object.base_model_override or \
                                 APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash")

            session_to_use = create_new_chat_session(
                db=db,
                telegram_chat_id=user_id,
                telegram_user_id=user_id,
                active_prompt_id=active_prompt_object.id,
                current_base_model=default_base_model
            )

        if not session_to_use or not session_to_use.active_prompt:
            log.error(f"Failed to obtain a valid session or prompt for user {user_id}.")
            return "抱歉，无法初始化AI对话设置。"

        current_prompt_config = session_to_use.active_prompt
        current_base_model_for_session = session_to_use.current_base_model
        deserialized_history = get_deserialized_chat_history(session_to_use)

        log.debug(
            f"Using session ID {session_to_use.id} for user {user_id} with prompt '{current_prompt_config.name}' "
            f"and model '{current_base_model_for_session}'. History items: {len(deserialized_history or [])}")

        chat_session_instance = gemini_service.start_chat_session(
            prompt_config=current_prompt_config,
            session_base_model=current_base_model_for_session,
            serialized_history=deserialized_history
        )

        if not chat_session_instance:
            log.error(
                f"Failed to start/resume Gemini chat session for user {user_id} with prompt '{current_prompt_config.name}'.")
            return "抱歉，连接到AI服务时出现问题，请稍后再试。"

        log.debug(f"Sending message to Gemini for user {user_id} (session ID {session_to_use.id}): '{message_text}'")
        bot_response_text, updated_serializable_history = await gemini_service.send_message(
            chat_session=chat_session_instance,
            message_text=message_text
        )

        if updated_serializable_history is not None:
            update_chat_history(
                db=db,
                session_id=session_to_use.id,
                new_gemini_chat_history=updated_serializable_history
            )
            log.debug(f"Chat history updated for session ID {session_to_use.id} (user {user_id}).")
        else:
            log.warning(
                f"Gemini service did not return an updated history for session ID {session_to_use.id}. History not saved.")

        return bot_response_text if bot_response_text else "抱歉，AI未能生成回复。"

    except Exception as e:
        log.error(f"Error in handle_private_message for user {user_id}: {e}", exc_info=True)
        if db:
            db.rollback()
        return "抱歉，处理您的消息时发生了意外错误。"
    finally:
        if db:
            db.close()