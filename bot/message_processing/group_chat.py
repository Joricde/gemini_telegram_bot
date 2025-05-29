# bot/message_processing/group_chat.py
import datetime
from typing import Optional  # इंश्योर करें Optional इंपोर्ट किया गया है

from telegram import Update
from telegram.ext import ContextTypes

from bot.utils import log
from bot.database import SessionLocal, models as db_models
from bot.database.models import PromptType
from bot.database.crud import (
    get_or_create_user,
    get_group_setting,
    create_or_update_group_setting,
    get_active_chat_session_state,
    create_new_chat_session,
    update_chat_history,
    get_deserialized_chat_history,
    get_prompt_by_id  # For fetching the group role prompt
)
from bot import APP_CONFIG, GEMINI_SETTINGS, GROUP_CHAT_SETTINGS  # Import GROUP_CHAT_SETTINGS
from bot.gemini_service import GeminiService


def _get_default_private_prompt_id(db: SessionLocal) -> Optional[int]:
    # ... (函数体保持不变) ...
    default_prompt_key = APP_CONFIG.get("default_bot_behavior", {}).get("default_private_prompt_key", "none_prompt")
    default_system_prompt_object = db.query(db_models.Prompt).filter(
        db_models.Prompt.name == default_prompt_key,
        db_models.Prompt.is_system_default == True,
        db_models.Prompt.prompt_type == PromptType.PRIVATE
    ).first()

    if not default_system_prompt_object:
        log.error(f"Default private prompt key '{default_prompt_key}' not found in DB or not of type PRIVATE.")
        default_system_prompt_object = db.query(db_models.Prompt).filter(
            db_models.Prompt.is_system_default == True,
            db_models.Prompt.prompt_type == PromptType.PRIVATE
        ).order_by(db_models.Prompt.id).first()
        if not default_system_prompt_object:
            log.critical(
                f"CRITICAL: No system default private prompts available in DB. Cannot create group individual session.")
            return None
    return default_system_prompt_object.id


async def _get_default_group_role_prompt(db: SessionLocal) -> Optional[db_models.Prompt]:
    """Helper to get the default GROUP_ROLE_PAYLOAD prompt object."""
    default_key = APP_CONFIG.get("default_bot_behavior", {}).get("default_group_role_prompt_key",
                                                                 "neutral_group_member")
    prompt_obj = db.query(db_models.Prompt).filter(
        db_models.Prompt.name == default_key,
        db_models.Prompt.is_system_default == True,
        db_models.Prompt.prompt_type == PromptType.GROUP_ROLE_PAYLOAD
    ).first()
    if not prompt_obj:
        log.error(
            f"Default group role prompt key '{default_key}' not found or not GROUP_ROLE_PAYLOAD. Trying any system group role.")
        prompt_obj = db.query(db_models.Prompt).filter(
            db_models.Prompt.is_system_default == True,
            db_models.Prompt.prompt_type == PromptType.GROUP_ROLE_PAYLOAD
        ).order_by(db_models.Prompt.id).first()
    return prompt_obj


async def handle_group_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message or not update.message.from_user or not update.message.text or not context.bot.username:
        log.info("Group interaction: key information missing.")
        return

    group_id = str(update.effective_chat.id)
    user_telegram_obj = update.message.from_user
    user_id = str(user_telegram_obj.id)  # User who sent the message
    message_text = update.message.text
    bot_username = context.bot.username

    processed_message_text = message_text.replace(f"@{bot_username}", "").strip()
    if not processed_message_text:
        await update.message.reply_text("你好！我在。有什么可以帮助你的吗？")
        return

    log.info(
        f"Handling group interaction from user {user_id} in group {group_id}. Processed msg: '{processed_message_text[:50]}'")

    db = SessionLocal()
    try:
        db_user = get_or_create_user(db, user_id=user_id, username=user_telegram_obj.username,
                                     first_name=user_telegram_obj.first_name, last_name=user_telegram_obj.last_name)
        group_setting = get_group_setting(db, group_id)

        if not group_setting:
            default_mode = APP_CONFIG.get("default_bot_behavior", {}).get("group_chat_mode", "individual")
            log.info(f"No settings for group {group_id}. Creating with default mode: {default_mode}")
            group_setting = create_or_update_group_setting(db, group_id=group_id, current_mode=default_mode)
            if not group_setting:
                log.error(f"Failed to create group_setting for group {group_id}")
                await update.message.reply_text("抱歉，初始化群组设置时发生错误。")
                return

        log.info(f"Group {group_id} mode: {group_setting.current_mode}. User: {user_id} (sender).")

        gemini_service_instance: Optional[GeminiService] = context.bot_data.get("gemini_service")
        if not isinstance(gemini_service_instance, GeminiService):
            log.error("GeminiService not found in bot_data for group chat.")
            await update.message.reply_text("抱歉，AI服务当前不可用。")
            return

        current_utc_time = datetime.datetime.now(datetime.timezone.utc)
        session_timeout_seconds = APP_CONFIG.get("default_bot_behavior", {}).get("session_timeout_seconds", 3600)
        session_to_use: Optional[db_models.ChatSessionState] = None

        # --- Individual Mode Logic (from 4.2, assumed mostly correct) ---
        if group_setting.current_mode == "individual":
            # ... (大部分 individual 模式的会话创建/恢复逻辑保持不变) ...
            # 确保 active_session 是基于 (group_id, user_id) 查询的
            active_session = get_active_chat_session_state(db, telegram_chat_id=group_id, telegram_user_id=user_id)
            default_prompt_id_for_session = None

            if active_session:
                if active_session.active_prompt and active_session.active_prompt.prompt_type != PromptType.PRIVATE:
                    active_session = None
                if active_session and active_session.last_interaction_at:
                    # ... (超时判断) ...
                    if (current_utc_time - active_session.last_interaction_at.replace(
                            tzinfo=datetime.timezone.utc)).total_seconds() > session_timeout_seconds:
                        default_prompt_id_for_session = active_session.active_prompt_id
                        session_to_use = create_new_chat_session(db, group_id, default_prompt_id_for_session,
                                                                 active_session.current_base_model, user_id)
                    else:
                        session_to_use = active_session
                elif active_session:
                    session_to_use = active_session

            if not session_to_use:
                default_prompt_id_for_session = _get_default_private_prompt_id(db)
                if not default_prompt_id_for_session:
                    await update.message.reply_text("抱歉，无法找到默认的AI角色来开始对话。")
                    return

                prompt_obj_for_model = db.query(db_models.Prompt).filter(
                    db_models.Prompt.id == default_prompt_id_for_session).first()
                default_base_model = (prompt_obj_for_model.base_model_override if prompt_obj_for_model else None) or \
                                     GEMINI_SETTINGS.get("default_base_model", "gemini-1.5-flash-latest")
                session_to_use = create_new_chat_session(db, group_id, default_prompt_id_for_session,
                                                         default_base_model, user_id)

            if not session_to_use or not session_to_use.active_prompt or session_to_use.active_prompt.prompt_type != PromptType.PRIVATE:
                # ... (错误处理) ...
                log.error(
                    f"Failed to obtain valid individual session or prompt for user {user_id} in group {group_id}.")
                await update.message.reply_text("抱歉，初始化AI对话设置时发生错误(I)。")
                return

            # --- Interaction for Individual Mode ---
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            chat_session_instance = gemini_service_instance.start_chat_session(
                prompt_config=session_to_use.active_prompt,  # PRIVATE type prompt
                session_base_model=session_to_use.current_base_model,
                serialized_history=get_deserialized_chat_history(session_to_use),
                group_role_payload_instruction=None
            )
            # ... (发送消息，更新历史，回复 - 与 4.2 中类似) ...
            if not chat_session_instance:  # 添加错误处理
                log.error(f"Failed to start Gemini session for individual mode in group {group_id}, user {user_id}")
                await update.message.reply_text("抱歉，连接AI服务时出错(I)。")
                return

            bot_response_text, updated_history = await gemini_service_instance.send_message(chat_session_instance,
                                                                                            processed_message_text)
            if updated_history: update_chat_history(db, session_to_use.id, updated_history)
            await update.message.reply_text(bot_response_text or "AI未能生成回复(I)。")

        # --- Shared Mode Logic (NEW for 4.4) ---
        elif group_setting.current_mode == "shared":
            log.info(f"Group {group_id} is in 'shared' mode. Bot mentioned by {user_id}.")

            active_session = get_active_chat_session_state(db, telegram_chat_id=group_id,
                                                           telegram_user_id=None)  # telegram_user_id is None for shared
            group_role_prompt: Optional[db_models.Prompt] = None

            if active_session:
                # Shared session active_prompt should be GROUP_ROLE_PAYLOAD
                if active_session.active_prompt and active_session.active_prompt.prompt_type != PromptType.GROUP_ROLE_PAYLOAD:
                    log.warning(
                        f"Shared session ID {active_session.id} for group {group_id} has non-GROUP_ROLE_PAYLOAD prompt. Resetting.")
                    active_session = None  # Force re-creation with correct prompt type

                if active_session and active_session.last_interaction_at:
                    if (current_utc_time - active_session.last_interaction_at.replace(
                            tzinfo=datetime.timezone.utc)).total_seconds() > session_timeout_seconds:
                        log.info(
                            f"Shared session ID {active_session.id} for group {group_id} timed out. Creating new session.")
                        # Reuse existing prompt if valid, otherwise fetch default
                        if active_session.active_prompt and active_session.active_prompt.prompt_type == PromptType.GROUP_ROLE_PAYLOAD:
                            group_role_prompt = active_session.active_prompt
                        else:  # Fallback if somehow the timed-out session had a bad prompt
                            group_role_prompt = await _get_default_group_role_prompt(db)

                        current_base_model = active_session.current_base_model  # Reuse base model
                        active_session = None  # Mark for recreation
                    else:
                        session_to_use = active_session
                        group_role_prompt = session_to_use.active_prompt  # Should be GROUP_ROLE_PAYLOAD
                elif active_session:
                    session_to_use = active_session
                    group_role_prompt = session_to_use.active_prompt

            if not session_to_use:  # No active shared session, or it was invalidated/timed out
                log.info(f"No valid active shared session for group {group_id}. Creating new.")
                if not group_role_prompt:  # If not determined from a timed-out session's prompt
                    if group_setting.shared_mode_role_prompt_id:
                        prompt_from_setting = get_prompt_by_id(db, group_setting.shared_mode_role_prompt_id)
                        if prompt_from_setting and prompt_from_setting.prompt_type == PromptType.GROUP_ROLE_PAYLOAD:
                            group_role_prompt = prompt_from_setting
                        else:
                            log.warning(
                                f"Group {group_id} has invalid shared_mode_role_prompt_id {group_setting.shared_mode_role_prompt_id}. Using default.")
                            group_role_prompt = await _get_default_group_role_prompt(db)
                    else:
                        group_role_prompt = await _get_default_group_role_prompt(db)

                if not group_role_prompt:
                    await update.message.reply_text("抱歉，无法找到合适的群聊角色来开始对话。请管理员设置群聊角色。")
                    return

                current_base_model = (group_role_prompt.base_model_override or
                                      GEMINI_SETTINGS.get("default_base_model", "gemini-1.5-flash-latest"))

                session_to_use = create_new_chat_session(
                    db=db,
                    telegram_chat_id=group_id,
                    telegram_user_id=None,  # Crucial for shared session
                    active_prompt_id=group_role_prompt.id,
                    current_base_model=current_base_model
                )

            if not session_to_use or not session_to_use.active_prompt or \
                    session_to_use.active_prompt.prompt_type != PromptType.GROUP_ROLE_PAYLOAD:
                log.error(f"Failed to obtain valid shared session or GROUP_ROLE_PAYLOAD prompt for group {group_id}.")
                await update.message.reply_text("抱歉，初始化群聊共享AI对话设置时发生错误(S)。")
                return

            # The actual group role prompt (payload provider)
            final_group_role_prompt_payload_provider = session_to_use.active_prompt

            # --- Input Formatting for Gemini (Shared Mode) ---
            # Example: Prepend username. Defined by GROUP_CHAT_SETTINGS.default_system_headers_template's INPUT_FORMAT
            # For now, let's assume a simple format. This can be made more configurable.
            # The template itself might guide Gemini on how to expect input.
            # For example, if template says INPUT_FORMAT: "{username}: {message_content}"
            # GeminiService would need to be aware, or we format it here.
            # Current GeminiService doesn't use INPUT_FORMAT directly for message sending.
            # Let's just pass the processed_message_text for now.
            # The system_instruction (headers + payload) will guide its persona.
            message_to_gemini = f"{user_telegram_obj.first_name or user_telegram_obj.username or 'User'}: {processed_message_text}"
            # A more advanced way would be to pass user details to GeminiService if the model is to be aware of who said what.
            # Or, the history itself contains user identifiers if it's a multi-turn shared chat.

            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

            chat_session_instance = gemini_service_instance.start_chat_session(
                prompt_config=final_group_role_prompt_payload_provider,  # This is the GROUP_ROLE_PAYLOAD prompt
                session_base_model=session_to_use.current_base_model,
                serialized_history=get_deserialized_chat_history(session_to_use),
                group_role_payload_instruction=final_group_role_prompt_payload_provider.system_instruction
                # Pass the payload
            )

            if not chat_session_instance:
                log.error(f"Failed to start Gemini session for shared mode in group {group_id}")
                await update.message.reply_text("抱歉，连接AI服务时出错(S)。")
                return

            # Send the message (potentially formatted with username)
            bot_response_text, updated_serializable_history = await gemini_service_instance.send_message(
                chat_session=chat_session_instance,
                message_text=message_to_gemini  # Use the potentially formatted message
            )

            if updated_serializable_history is not None:
                update_chat_history(
                    db=db,
                    session_id=session_to_use.id,
                    new_gemini_chat_history=updated_serializable_history
                )
                log.debug(f"Shared chat history updated for session ID {session_to_use.id} (group {group_id}).")
            else:
                log.warning(
                    f"Gemini service did not return updated history for shared session ID {session_to_use.id}. History not saved.")

            if bot_response_text:
                await update.message.reply_text(bot_response_text)
            else:
                await update.message.reply_text("抱歉，AI未能生成回复(S)。")

        else:  # Unknown mode
            log.warning(f"Group {group_id} has an unknown mode: {group_setting.current_mode}")
            await update.message.reply_text("当前群组模式未知，无法处理。")

    except Exception as e:
        log.error(f"Error in handle_group_interaction for group {group_id}, user {user_id}: {e}", exc_info=True)
    finally:
        if db: db.close()


async def set_group_chat_mode(group_id: str, new_mode: str) -> str:
    # ... (函数体保持不变) ...
    valid_modes = ["individual", "shared"]
    if new_mode not in valid_modes:
        return f"无效的模式 '{new_mode}'。可用模式: {', '.join(valid_modes)}。"

    db = SessionLocal()
    try:
        # Get current setting to see if mode is actually changing
        # old_setting = get_group_setting(db, group_id)
        # old_mode = old_setting.current_mode if old_setting else None

        group_setting = create_or_update_group_setting(db, group_id=group_id, current_mode=new_mode)

        if group_setting and group_setting.current_mode == new_mode:
            log.info(f"Group {group_id} mode successfully changed to '{new_mode}'.")

            # Consider archiving sessions when mode changes
            # if old_mode and old_mode != new_mode:
            # log.info(f"Mode changed for group {group_id} from {old_mode} to {new_mode}. Archiving previous mode sessions.")
            # if old_mode == "shared": # Was shared, now individual or other
            # crud.archive_previous_active_sessions(db, telegram_chat_id=group_id, telegram_user_id=None)
            # elif old_mode == "individual": # Was individual, now shared or other
            # You might need a new CRUD function to archive all individual sessions for a group.
            # For now, we'll let them time out.
            # pass

            db.commit()  # Commit a second time if archive_previous_active_sessions did a commit.
            # Or ensure create_or_update_group_setting doesn't commit if further ops are needed.
            # Best to have set_group_chat_mode manage its own transaction.
            return f"群聊模式已成功设置为: **{new_mode}**。"
        else:
            log.error(f"Failed to update mode for group {group_id} to '{new_mode}'.")
            return f"设置群聊模式时发生错误。"
    except Exception as e:
        log.error(f"Exception setting group chat mode for {group_id} to {new_mode}: {e}", exc_info=True)
        db.rollback()
        return "设置群聊模式时发生意外错误。"
    finally:
        db.close()


from bot.database.crud import (
    # ... (其他 CRUD imports) ...
    get_prompt_by_id,
    get_system_prompt_by_name,  # For looking up system group roles by name
    archive_previous_active_sessions  # To reset shared session after prompt change
)
from bot.database.models import PromptType  # Ensure PromptType is imported


# ... (其他函数如 _get_default_private_prompt_id, _get_default_group_role_prompt, handle_group_interaction, set_group_chat_mode) ...

async def set_group_shared_role_prompt(group_id: str, prompt_identifier: str) -> str:
    """
    Sets the shared mode role prompt for a given group.
    'prompt_identifier' can be a prompt ID (integer) or a system prompt name (string).
    Returns a confirmation or error message.
    """
    db = SessionLocal()
    try:
        prompt_to_set: Optional[db_models.Prompt] = None

        # Try to parse identifier as ID first
        try:
            prompt_id_candidate = int(prompt_identifier)
            prompt_to_set = get_prompt_by_id(db, prompt_id_candidate)
        except ValueError:
            # Not an integer, so treat as a system prompt name
            prompt_to_set = get_system_prompt_by_name(db, name=prompt_identifier)

        if not prompt_to_set:
            return f"未找到标识为 '{prompt_identifier}' 的角色。请提供有效的角色ID或系统预设角色名称。"

        if prompt_to_set.prompt_type != PromptType.GROUP_ROLE_PAYLOAD:
            return f"角色 '{prompt_to_set.name}' (ID: {prompt_to_set.id}) 不是有效的群聊角色类型 (GROUP_ROLE_PAYLOAD)。无法设置为群聊共享角色。"

        # If the prompt is a system default, it's fine.
        # If we were to allow user-created GROUP_ROLE_PAYLOAD prompts, additional checks might be needed here (e.g., ownership or public availability).
        # For now, only system GROUP_ROLE_PAYLOAD prompts are effectively settable this way unless ID is known for a user-created one (which isn't an implemented flow yet for group roles).

        group_setting = create_or_update_group_setting(db, group_id=group_id,
                                                       shared_mode_role_prompt_id=prompt_to_set.id)

        if group_setting and group_setting.shared_mode_role_prompt_id == prompt_to_set.id:
            log.info(
                f"Group {group_id} shared mode prompt successfully set to '{prompt_to_set.name}' (ID: {prompt_to_set.id}).")

            # Archive the current shared session for this group to apply the new prompt immediately on next interaction
            if archive_previous_active_sessions(db, telegram_chat_id=group_id, telegram_user_id=None):
                log.info(f"Archived active shared session for group {group_id} due to prompt change.")
                db.commit()  # Commit archiving
            else:
                # No active shared session to archive, or an error occurred during archival.
                # create_or_update_group_setting already committed the prompt_id change.
                pass

            return f"群聊共享角色已成功设置为: **{prompt_to_set.name}**。\n下次在共享模式下与我互动时，我将以这个新角色出现。"
        else:
            log.error(
                f"Failed to update shared_mode_role_prompt_id for group {group_id} to prompt ID {prompt_to_set.id}.")
            return f"设置群聊共享角色时发生错误。"

    except Exception as e:
        log.error(
            f"Exception setting group shared role prompt for {group_id} with identifier '{prompt_identifier}': {e}",
            exc_info=True)
        db.rollback()  # Rollback in case create_or_update_group_setting hasn't or if archive failed before its commit
        return "设置群聊共享角色时发生意外错误。"
    finally:
        db.close()


import random  # Add random for probability
from bot.database.crud import get_recent_messages_from_cache  # Import this
from bot.database.models import Prompt as PromptModel  # For type hinting prompt object


# ... (existing functions: _get_default_private_prompt_id, _get_default_group_role_prompt, handle_group_interaction, set_group_chat_mode, set_group_shared_role_prompt)


async def handle_potential_random_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles a non-mention group message to decide if a random reply should be triggered.
    """
    if not update.effective_chat or not update.message:  # Basic check
        return

    group_id = str(update.effective_chat.id)

    db = SessionLocal()
    try:
        group_setting = get_group_setting(db, group_id)
        if not group_setting:
            default_mode = APP_CONFIG.get("default_bot_behavior", {}).get("group_chat_mode", "individual")
            log.info(f"No settings for group {group_id} during random reply check. Creating defaults.")
            group_setting = create_or_update_group_setting(db, group_id=group_id, current_mode=default_mode)
            if not group_setting:
                log.error(f"Could not get or create group settings for {group_id} for random reply.")
                return

        if not group_setting.current_mode == "shared" or not group_setting.random_reply_enabled:
            return

        random_params = APP_CONFIG.get("group_chat_settings", {}).get("random_reply_parameters", {})
        listen_count = random_params.get("listen_message_count", 7)
        prob_denominator = random_params.get("base_probability_p_denominator", 25)

        if prob_denominator <= 0:
            log.warning(
                f"Group {group_id}: base_probability_p_denominator is invalid ({prob_denominator}). Disabling random reply.")
            return

        should_trigger = random.randrange(0, prob_denominator) == 0
        log.debug(f"Group {group_id}: Random reply check. Trigger: {should_trigger} (1/{prob_denominator})")

        if not should_trigger:
            return

        log.info(f"Group {group_id}: Random reply triggered!")

        gemini_service_instance: Optional[GeminiService] = context.bot_data.get("gemini_service")
        if not isinstance(gemini_service_instance, GeminiService):
            log.error("GeminiService not found in bot_data for random reply.")
            return

        shared_group_role_prompt: Optional[PromptModel] = None
        if group_setting.shared_mode_role_prompt_id:
            prompt_from_setting = get_prompt_by_id(db, group_setting.shared_mode_role_prompt_id)
            if prompt_from_setting and prompt_from_setting.prompt_type == PromptType.GROUP_ROLE_PAYLOAD:
                shared_group_role_prompt = prompt_from_setting

        if not shared_group_role_prompt:
            shared_group_role_prompt = await _get_default_group_role_prompt(db)

        if not shared_group_role_prompt:
            log.error(f"Group {group_id}: Cannot find a suitable group role prompt for random reply.")
            return

        context_message_count = listen_count
        recent_messages_db = get_recent_messages_from_cache(db, group_id, limit=context_message_count)

        if not recent_messages_db:
            log.info(f"Group {group_id}: No recent messages in cache for random reply context.")
            return

        history_for_gemini_session: list[dict] = []
        for msg_db in reversed(recent_messages_db):  # Oldest first
            # 修改这里：使用 user_id 而不是 sender_name
            # msg_db.user_id 是 GroupMessageCache 模型中的字段
            # 它本身就是一个字符串或None
            user_identifier = f"User {msg_db.user_id}" if msg_db.user_id else "UnknownUser"

            # 确保 msg_db.text 不为 None，如果可能为空，则提供默认值
            message_content = msg_db.text if msg_db.text is not None else ""

            history_for_gemini_session.append({
                "role": "user",
                "parts": [{"text": f"{user_identifier}: {message_content}"}]
            })

        if not history_for_gemini_session:
            log.info(f"Group {group_id}: Formatted history for random reply is empty.")
            return

        log.debug(
            f"Group {group_id}: Context for random reply (last {len(history_for_gemini_session)} msgs): {history_for_gemini_session[-1] if history_for_gemini_session else 'None'}")

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        current_base_model = (shared_group_role_prompt.base_model_override or
                              GEMINI_SETTINGS.get("default_base_model", "gemini-1.5-flash-latest"))

        chat_session_instance_random = gemini_service_instance.start_chat_session(
            prompt_config=shared_group_role_prompt,
            session_base_model=current_base_model,
            serialized_history=history_for_gemini_session,
            group_role_payload_instruction=shared_group_role_prompt.system_instruction
        )

        if not chat_session_instance_random:
            log.error(f"Failed to start Gemini session for random reply in group {group_id}")
            return

        trigger_message_for_random_reply = "..."

        bot_response_text, _ = await gemini_service_instance.send_message(
            chat_session=chat_session_instance_random,
            message_text=trigger_message_for_random_reply
        )

        if bot_response_text:
            log.info(f"Group {group_id}: Sending random reply: '{bot_response_text[:50]}...'")
            await context.bot.send_message(chat_id=group_id, text=bot_response_text)
        else:
            log.info(f"Group {group_id}: AI did not generate a random reply.")

    except Exception as e:
        log.error(f"Error in handle_potential_random_reply for group {group_id}: {e}", exc_info=True)
    finally:
        if db: db.close()