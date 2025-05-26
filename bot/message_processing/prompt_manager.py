# bot/message_processing/prompt_manager.py

from sqlalchemy.orm import Session
from typing import Optional, List  # Keep List if other functions use it

from bot import APP_CONFIG, PROMPTS_CONFIG
from bot.database import SessionLocal
from bot.database import models as db_models
from bot.database.crud import (
    create_prompt,
    get_prompts_by_user,  # Still used by upload logic for collision check
    get_system_default_prompts,  # May not be directly used here anymore if list_my_prompts is removed
    get_prompt_by_name,
    get_prompt_by_id,
    # get_active_chat_session_state, # Not directly used here anymore if list_my_prompts is removed
    create_new_chat_session,
    get_or_create_user
)
from bot.utils import log

# --- Prompt Upload Logic ---
NAME, SYSTEM_INSTRUCTION = range(2)


async def start_upload_prompt(user_id: str) -> str:
    db = SessionLocal()
    try:
        get_or_create_user(db, user_id=user_id)
    finally:
        db.close()
    return "请发送你想要定义的角色的**系统指令 (System Instruction)**。\n例如：你是一个乐于助人的助手。"


async def received_system_instruction(user_id: str, instruction: str, context_user_data: dict) -> str:
    context_user_data['system_instruction'] = instruction
    return "很好！现在请为这个角色设定一个**唯一的名称**。\n例如：我的助手"


async def received_prompt_name_and_create(user_id: str, name: str, context_user_data: dict) -> str:
    system_instruction = context_user_data.get('system_instruction')
    if not system_instruction:
        log.warning(f"System instruction not found in user_data for user {user_id} during prompt creation.")
        return "抱歉，发生错误，找不到系统指令。请重新开始 /upload_prompt。"

    db = SessionLocal()
    try:
        existing_prompt_system = get_prompt_by_name(db, name=name)
        if existing_prompt_system and (
                existing_prompt_system.is_system_default or existing_prompt_system.creator_user_id != user_id):
            if existing_prompt_system.is_system_default:
                return f"角色名称 '{name}' 与系统预设角色冲突，请换一个名称。"

        user_prompts = get_prompts_by_user(db, user_id=user_id)  #
        if any(p.name == name for p in user_prompts):
            return f"你已经创建过一个名为 '{name}' 的角色了。请换一个名称，或使用 /my_prompts 查看。"

        if existing_prompt_system and not existing_prompt_system.is_system_default and existing_prompt_system.creator_user_id != user_id:
            return f"角色名称 '{name}' 已被其他用户使用，请选择一个不同的名称。"

        default_gen_params = APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})
        new_prompt = create_prompt(
            db=db,
            name=name,
            system_instruction=system_instruction,
            creator_user_id=user_id,
            temperature=default_gen_params.get("temperature"),
            top_p=default_gen_params.get("top_p"),
            top_k=default_gen_params.get("top_k"),
            max_output_tokens=default_gen_params.get("max_output_tokens"),
            is_system_default=False
        )
        if new_prompt:
            log.info(f"User {user_id} created new prompt '{name}' (ID: {new_prompt.id}).")
            context_user_data.clear()
            return (f"角色 '{name}' 创建成功！\n"
                    f"你可以使用 /my_prompts 查看并选择它。")
        else:
            return "创建角色时发生错误，可能是名称已存在或其他数据库问题。请稍后再试或更改名称。"
    except Exception as e:
        log.error(f"Exception creating prompt '{name}' for user {user_id}: {e}", exc_info=True)
        return "创建角色时发生意外错误。"
    finally:
        db.close()


async def cancel_upload_prompt(user_id: str, context_user_data: dict) -> str:
    context_user_data.clear()
    log.info(f"User {user_id} cancelled prompt upload.")
    return "角色创建已取消。"


# list_my_prompts function is now effectively handled by my_prompts_command_handler in handlers.py
# You can remove it from here if it's not used elsewhere.
# async def list_my_prompts(user_id: str) -> str:
# ... (previous code)


# --- Set Prompt Logic ---
async def set_active_prompt(user_id: str, prompt_identifier: str) -> str:  # prompt_identifier can be an ID string
    """Sets the active prompt for the user's private chat by creating a new session."""
    db = SessionLocal()
    try:
        prompt_to_set: Optional[db_models.Prompt] = None
        if prompt_identifier.isdigit():  # Identifier is an ID
            prompt_to_set = get_prompt_by_id(db, prompt_id=int(prompt_identifier))
        else:  # Identifier is a name (though we are mostly using IDs via buttons now)
            prompt_to_set = get_prompt_by_name(db, name=prompt_identifier)

        if not prompt_to_set:
            return f"找不到角色 (ID/名称: '{prompt_identifier}')。可能已被删除或输入错误。"

        if not prompt_to_set.is_system_default and prompt_to_set.creator_user_id != user_id:
            return f"你无法设置角色 '{prompt_to_set.name}'，因为它不属于你，也不是系统预设角色。"

        new_base_model = prompt_to_set.base_model_override or \
                         APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash")

        get_or_create_user(db, user_id=user_id)

        new_session = create_new_chat_session(
            db=db,
            telegram_chat_id=user_id,
            telegram_user_id=user_id,
            active_prompt_id=prompt_to_set.id,
            current_base_model=new_base_model
        )

        if new_session:
            log.info(
                f"User {user_id} switched to prompt '{prompt_to_set.name}' (ID: {prompt_to_set.id}). New session ID {new_session.id} created.")
            return (f"已切换到角色: **{prompt_to_set.name}**。\n"
                    "与TA的新对话已经开始！")
        else:
            log.error(f"Failed to create new session when user {user_id} tried to set prompt '{prompt_to_set.name}'.")
            return "切换角色时发生错误，未能创建新的对话会话。"

    except Exception as e:
        log.error(f"Error setting active prompt '{prompt_identifier}' for user {user_id}: {e}", exc_info=True)
        if db:
            db.rollback()
        return "设置角色时发生意外错误。"
    finally:
        if db:
            db.close()