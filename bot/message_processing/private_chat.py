from sqlalchemy.orm import Session
from typing import Optional

from bot.database import SessionLocal
from bot.database import models as db_models
from bot.database.crud import (
    get_or_create_user,
    get_chat_session_state,
    create_or_update_chat_session_state,
    get_deserialized_chat_history,
    get_prompt_by_name,  # To get the default prompt
    get_prompt_by_id
)
from bot.gemini_service import GeminiService
from bot.utils import log
from bot import APP_CONFIG, PROMPTS_CONFIG  # For default prompt key and Gemini settings


async def handle_private_message(
        user_id: str,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
        message_text: str,
        gemini_service: GeminiService
) -> Optional[str]:
    """
    Handles an incoming private message, interacts with Gemini, and updates the database.

    Returns:
        The text response from Gemini, or None if an error occurred.
    """
    db: Optional[Session] = None
    try:
        db = SessionLocal()

        # 1. Get or create user
        db_user = get_or_create_user(db, user_id=user_id, username=username, first_name=first_name, last_name=last_name)
        if not db_user:
            log.error(f"Failed to get or create user {user_id} in private_chat.")
            return "抱歉，处理您的用户信息时出现问题。"

        # 2. Get or create ChatSessionState
        # For private chat, telegram_chat_id is the same as telegram_user_id
        session_state = get_chat_session_state(db, telegram_chat_id=user_id, telegram_user_id=user_id)

        active_prompt: Optional[db_models.Prompt] = None
        current_base_model: Optional[str] = None
        deserialized_history: Optional[list] = None

        if session_state:
            active_prompt = get_prompt_by_id(db, prompt_id=session_state.active_prompt_id)
            current_base_model = session_state.current_base_model
            deserialized_history = get_deserialized_chat_history(session_state)
            log.debug(
                f"Resuming session for user {user_id} with prompt '{active_prompt.name if active_prompt else 'N/A'}' and model '{current_base_model}'. History items: {len(deserialized_history or [])}")

        if not active_prompt:  # If no session or prompt in session is invalid
            default_prompt_key = APP_CONFIG.get("default_bot_behavior", {}).get("default_prompt_key", "none_prompt")
            active_prompt = get_prompt_by_name(db, name=PROMPTS_CONFIG.get(default_prompt_key, {}).get("name",
                                                                                                       default_prompt_key))
            if not active_prompt:  # Fallback if name lookup fails (e.g. prompt_key is the name)
                active_prompt = get_prompt_by_name(db, name=default_prompt_key)

            if not active_prompt:
                log.error(f"Default prompt '{default_prompt_key}' not found in database for user {user_id}.")
                return "抱歉，我当前没有可用的默认角色设置。"
            log.info(
                f"No active session or valid prompt for user {user_id}. Using default prompt: '{active_prompt.name}'")

        if not current_base_model:
            current_base_model = active_prompt.base_model_override or \
                                 APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-2.0-flash")
            log.info(
                f"No current base model for user {user_id}. Using: '{current_base_model}' based on prompt or default.")

        # 3. Start/Resume Gemini ChatSession
        chat_session = gemini_service.start_chat_session(
            prompt_config=active_prompt,
            session_base_model=current_base_model,
            serialized_history=deserialized_history
        )

        if not chat_session:
            log.error(
                f"Failed to start/resume Gemini chat session for user {user_id} with prompt '{active_prompt.name}'.")
            return "抱歉，连接到AI服务时出现问题，请稍后再试。"

        # 4. Send user's message to Gemini
        log.debug(f"Sending message to Gemini for user {user_id}: '{message_text}'")
        bot_response_text, updated_serializable_history = await gemini_service.send_message(
            chat_session=chat_session,
            message_text=message_text
        )

        if bot_response_text is None:  # Indicates an error during Gemini interaction
            log.error(f"Gemini service returned no response or an error for user {user_id}.")
            # updated_serializable_history might still be the old history or None
            # We should probably save the state even if response failed to keep user message
            if updated_serializable_history is None and deserialized_history is not None:
                # If send_message failed catastrophically and didn't even return old history, try to save at least the user's message
                # This part needs careful thought on how GeminiService's send_message error handling works for history
                pass  # For now, we'll rely on GeminiService to return history even on failure if possible.

        # 5. Save updated history to ChatSessionState
        # create_or_update_chat_session_state will handle if session_state was initially None
        create_or_update_chat_session_state(
            db=db,
            telegram_chat_id=user_id,
            telegram_user_id=user_id,
            active_prompt_id=active_prompt.id,
            current_base_model=current_base_model,  # This model was used for the last interaction
            gemini_chat_history=updated_serializable_history
        )
        log.debug(f"Chat session state updated for user {user_id}.")

        return bot_response_text if bot_response_text else "抱歉，AI未能生成回复。"

    except Exception as e:
        log.error(f"Error in handle_private_message for user {user_id}: {e}", exc_info=True)
        return "抱歉，处理您的消息时发生了意外错误。"
    finally:
        if db:
            db.close()