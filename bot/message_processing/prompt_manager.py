# bot/message_processing/prompt_manager.py

from sqlalchemy.orm import Session
from typing import Optional, List

from bot import APP_CONFIG, PROMPTS_CONFIG
from bot.database import SessionLocal
from bot.database import models as db_models
from bot.database.crud import (
    create_prompt,
    get_prompts_by_user,
    get_system_default_prompts,
    get_prompt_by_name,
    get_prompt_by_id,
    get_chat_session_state,
    create_or_update_chat_session_state,
    get_or_create_user
)
from bot.utils import log

# --- Prompt Upload Logic ---
NAME, SYSTEM_INSTRUCTION = range(2) # Stages for ConversationHandler

async def start_upload_prompt(user_id: str) -> str:
    """Initiates the prompt upload process."""
    db = SessionLocal()
    try:
        get_or_create_user(db, user_id=user_id) # Ensure user exists
    finally:
        db.close()
    return "请发送你想要定义的角色的**系统指令 (System Instruction)**。\n例如：你是一个乐于助人的助手。"

async def received_system_instruction(user_id: str, instruction: str, context_user_data: dict) -> str:
    """Stores the system instruction and asks for the prompt name."""
    context_user_data['system_instruction'] = instruction
    return "很好！现在请为这个角色设定一个**唯一的名称**。\n例如：我的助手"

async def received_prompt_name_and_create(user_id: str, name: str, context_user_data: dict) -> str:
    """Stores the prompt name, creates the prompt, and ends the conversation."""
    system_instruction = context_user_data.get('system_instruction')
    if not system_instruction:
        log.warning(f"System instruction not found in user_data for user {user_id} during prompt creation.")
        return "抱歉，发生错误，找不到系统指令。请重新开始 /upload_prompt。"

    db = SessionLocal()
    try:
        # Check if prompt name already exists (system or user-created for this user)
        existing_prompt_system = get_prompt_by_name(db, name=name)
        if existing_prompt_system and existing_prompt_system.is_system_default:
            return f"角色名称 '{name}' 与系统预设角色冲突，请换一个名称，或使用 /set_prompt 来设置预设角色。"

        existing_prompt_user_list = get_prompts_by_user(db, user_id=user_id)
        if any(p.name == name for p in existing_prompt_user_list):
            return f"你已经创建过一个名为 '{name}' 的角色了。请换一个名称，或使用 /my_prompts 查看。"


        default_gen_params = APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})
        # Use default generation parameters from app_config.yml
        new_prompt = create_prompt(
            db=db,
            name=name,
            system_instruction=system_instruction,
            creator_user_id=user_id,
            temperature=default_gen_params.get("temperature"),
            top_p=default_gen_params.get("top_p"),
            top_k=default_gen_params.get("top_k"),
            max_output_tokens=default_gen_params.get("max_output_tokens"),
            # base_model_override will use the global default from GeminiService if not set here
            is_system_default=False
        )
        if new_prompt:
            log.info(f"User {user_id} created new prompt '{name}' (ID: {new_prompt.id}).")
            context_user_data.clear() # Clear data after successful creation
            return (f"角色 '{name}' 创建成功！\n"
                    f"你可以使用 /my_prompts 查看，或使用 /set_prompt {name} 来激活它。")
        else:
            log.error(f"Failed to create prompt '{name}' for user {user_id} in DB.")
            return "创建角色时发生数据库错误，请稍后再试。"
    except Exception as e:
        log.error(f"Exception creating prompt '{name}' for user {user_id}: {e}", exc_info=True)
        return "创建角色时发生意外错误。"
    finally:
        db.close()

async def cancel_upload_prompt(user_id: str, context_user_data: dict) -> str:
    """Cancels the prompt upload process."""
    context_user_data.clear()
    log.info(f"User {user_id} cancelled prompt upload.")
    return "角色创建已取消。"

# --- List Prompts Logic ---
async def list_my_prompts(user_id: str) -> str:
    """Lists user-created and system default prompts."""
    db = SessionLocal()
    try:
        user_prompts = get_prompts_by_user(db, user_id=user_id)
        system_prompts = get_system_default_prompts(db)

        response_lines = ["📚 **可用的角色 (Prompts)**:\n"]

        active_session_state = get_chat_session_state(db, telegram_chat_id=user_id, telegram_user_id=user_id)
        active_prompt_id = active_session_state.active_prompt_id if active_session_state else None

        response_lines.append("--- 你创建的角色 ---")
        if user_prompts:
            for p in user_prompts:
                is_active = " (当前激活)" if p.id == active_prompt_id else ""
                response_lines.append(f"- `{p.name}`{is_active}")
        else:
            response_lines.append("_你还没有创建任何角色。使用 /upload_prompt 创建一个吧！_")

        response_lines.append("\n--- 系统预设角色 ---")
        if system_prompts:
            for p in system_prompts:
                is_active = " (当前激活)" if p.id == active_prompt_id else ""
                response_lines.append(f"- `{p.name}`{is_active}")
        else:
            response_lines.append("_没有可用的系统预设角色。_")

        response_lines.append(f"\n使用 `/set_prompt <角色名称>` 来切换角色。")
        return "\n".join(response_lines)
    finally:
        db.close()

# --- Set Prompt Logic ---
async def set_active_prompt(user_id: str, prompt_identifier: str) -> str:
    """Sets the active prompt for the user's private chat."""
    db = SessionLocal()
    try:
        # Try to get prompt by ID first if identifier is a number
        prompt_to_set: Optional[db_models.Prompt] = None
        if prompt_identifier.isdigit():
            prompt_to_set = get_prompt_by_id(db, prompt_id=int(prompt_identifier))

        # If not found by ID or identifier is not a number, try by name
        if not prompt_to_set:
            prompt_to_set = get_prompt_by_name(db, name=prompt_identifier)

        if not prompt_to_set:
            return f"找不到名为或ID为 '{prompt_identifier}' 的角色。请使用 /my_prompts 查看可用角色。"

        # Check if the prompt is either system default or created by the user
        if not prompt_to_set.is_system_default and prompt_to_set.creator_user_id != user_id:
            return f"你无法设置角色 '{prompt_identifier}'，因为它不属于你，也不是系统预设角色。"

        # Get current session state or create if it doesn't exist
        # (though it should exist if they are chatting)
        session_state = get_chat_session_state(db, telegram_chat_id=user_id, telegram_user_id=user_id)

        if session_state:
            if session_state.active_prompt_id == prompt_to_set.id:
                return f"角色 '{prompt_to_set.name}' 已经是你当前的激活角色了。"

            # Determine the base model for the new session
            new_base_model = prompt_to_set.base_model_override or \
                             APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash")

            create_or_update_chat_session_state(
                db=db,
                telegram_chat_id=user_id,
                telegram_user_id=user_id,
                active_prompt_id=prompt_to_set.id,
                current_base_model=new_base_model,
                gemini_chat_history=None  # Reset history when prompt changes
            )
            log.info(f"User {user_id} set active prompt to '{prompt_to_set.name}' (ID: {prompt_to_set.id}). Chat history reset.")
            return (f"已切换到角色: **{prompt_to_set.name}**。\n"
                    "与TA的新对话已经开始！")
        else:
            # This case should ideally not happen if user has interacted before /start
            # If it does, create a new session state with this prompt
            default_base_model = prompt_to_set.base_model_override or \
                                 APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash")
            get_or_create_user(db, user_id=user_id) # Ensure user exists
            create_or_update_chat_session_state(
                db=db,
                telegram_chat_id=user_id,
                telegram_user_id=user_id,
                active_prompt_id=prompt_to_set.id,
                current_base_model=default_base_model,
                gemini_chat_history=None
            )
            log.info(f"User {user_id} set initial active prompt to '{prompt_to_set.name}' (ID: {prompt_to_set.id}). New session created.")
            return (f"已为你设置初始角色: **{prompt_to_set.name}**。\n"
                    "现在可以开始对话了！")

    except Exception as e:
        log.error(f"Error setting active prompt '{prompt_identifier}' for user {user_id}: {e}", exc_info=True)
        return "设置角色时发生意外错误。"
    finally:
        db.close()