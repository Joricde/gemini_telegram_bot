# bot/message_processing/prompt_manager.py

from sqlalchemy.orm import Session
from typing import Dict, Optional

from bot import APP_CONFIG
from bot.database import SessionLocal
from bot.database import models as db_models
from bot.database.models import PromptType  # Import Enum
from bot.database.crud import (
    create_prompt,
    get_prompt_by_id_and_user,
    get_prompt_by_name_and_user,  # For checking name collision
    update_prompt_instruction,
    delete_prompt,
    create_new_chat_session,
    get_or_create_user  # To ensure user exists before prompt operations
)
from bot.utils import log

# --- Constants for ConversationHandler states ---
# For uploading a new private prompt
UPLOAD_PRIVATE_INSTRUCTION, UPLOAD_PRIVATE_NAME = range(2)
# For editing an existing private prompt
EDIT_PRIVATE_INSTRUCTION = range(2, 3)  # Start from next available integer


# --- Helper to get default generation parameters ---
def _get_default_gen_params() -> dict:
    return APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})


# --- Upload Private Prompt Logic ---
async def start_upload_private_prompt_flow(user_id: str, context_user_data: Dict) -> str:
    """Initiates the process for a user to upload a new private prompt."""
    context_user_data.clear()  # Clear any previous conversation data
    db = SessionLocal()
    try:
        get_or_create_user(db, user_id=user_id)  # Ensure user exists
    finally:
        db.close()
    return (
        "好的，我们来创建一个新的私人角色。\n\n"
        "请发送你想要定义的角色的**系统指令 (System Instruction)**。\n"
        "例如：`你是一个乐于助人的助手，总是以积极的口吻回答问题。`\n\n"
        "输入 /cancel 可以随时取消创建。"
    )


async def received_private_instruction_for_upload(user_id: str, instruction: str, context_user_data: Dict) -> str:
    """Stores the received system instruction and asks for the prompt name."""
    if not instruction.strip():
        return "系统指令不能为空，请重新发送你的系统指令，或使用 /cancel 取消。"
    context_user_data['private_instruction_to_upload'] = instruction
    return (
        "指令已收到！现在请为这个私人角色设定一个**唯一的名称**。\n"
        "例如：`我的私人助理`\n\n"
        "输入 /cancel 可以随时取消。"
    )


async def received_private_prompt_name_and_create(user_id: str, name: str, context_user_data: Dict) -> str:
    """Receives the prompt name and attempts to create the new private prompt."""
    name = name.strip()
    if not name:
        return "角色名称不能为空，请重新发送名称，或使用 /cancel 取消。"
    if len(name) > 50:  # Max name length check
        return "角色名称过长（最多50个字符），请换一个短一点的名称，或使用 /cancel 取消。"

    system_instruction = context_user_data.get('private_instruction_to_upload')
    if not system_instruction:
        log.warning(f"System instruction for upload not found in user_data for user {user_id}.")
        return "抱歉，发生内部错误，找不到之前输入的系统指令。请使用 /upload_prompt 重新开始。"

    db = SessionLocal()
    try:
        # Check if user already has a private prompt with this name
        existing_prompt = get_prompt_by_name_and_user(db, name=name, user_id=user_id, prompt_type=PromptType.PRIVATE)
        if existing_prompt:
            return f"你已经有一个名为 '{name}' 的私人角色了。请换一个名称，或使用 /my_prompts 查看并管理你的角色。"

        # Check for collision with system prompt names (optional, but good practice)
        system_prompt_collision = db.query(db_models.Prompt).filter(
            db_models.Prompt.name == name,
            db_models.Prompt.is_system_default == True
        ).first()
        if system_prompt_collision:
            return f"角色名称 '{name}' 与一个系统预设角色冲突，请换一个名称。"

        default_gen_params = _get_default_gen_params()
        new_prompt = create_prompt(
            db=db,
            name=name,
            system_instruction=system_instruction,
            prompt_type=PromptType.PRIVATE,
            creator_user_id=user_id,
            temperature=default_gen_params.get("temperature"),
            top_p=default_gen_params.get("top_p"),
            top_k=default_gen_params.get("top_k"),
            max_output_tokens=default_gen_params.get("max_output_tokens"),
            is_system_default=False  # User created prompts are not system defaults
        )
        if new_prompt:
            log.info(f"User {user_id} created new private prompt '{name}' (ID: {new_prompt.id}).")
            context_user_data.clear()
            return (f"私人角色 **'{name}'** 创建成功！🎉\n"
                    f"你可以使用 /my_prompts 命令来查看和选择它。")
        else:
            # create_prompt already logs errors if it returns None due to specific reasons
            return "创建私人角色时发生错误。可能是名称已被使用或数据库问题。请稍后再试或更改名称。"
    except Exception as e:
        log.error(f"Exception creating private prompt '{name}' for user {user_id}: {e}", exc_info=True)
        return "创建私人角色时发生意外错误，请稍后再试。"
    finally:
        db.close()
        context_user_data.pop('private_instruction_to_upload', None)  # Clean up


# --- Edit Private Prompt Logic ---
async def start_edit_private_prompt_flow(user_id: str, prompt_id_to_edit: int, context_user_data: Dict) -> str:
    """Initiates the editing process for a specific private prompt."""
    context_user_data.clear()
    db = SessionLocal()
    try:
        prompt = get_prompt_by_id_and_user(db, prompt_id=prompt_id_to_edit, user_id=user_id)
        if not prompt or prompt.prompt_type != PromptType.PRIVATE or prompt.is_system_default:
            return "无法编辑此角色：它可能不存在、不是你的私人角色或是一个不可编辑的系统预设角色。"

        context_user_data['prompt_id_to_edit'] = prompt_id_to_edit
        context_user_data['prompt_name_being_edited'] = prompt.name
        original_instruction_snippet = (prompt.system_instruction[:100] + '...') if len(
            prompt.system_instruction) > 100 else prompt.system_instruction
        return (
            f"你正在编辑私人角色：**{prompt.name}**。\n"
            f"当前的系统指令片段为：\n`{original_instruction_snippet}`\n\n"
            f"请输入**新的系统指令**。原来的指令将被完全替换。\n\n"
            f"输入 /cancel 可以随时取消编辑。"
        )
    finally:
        db.close()


async def received_new_instruction_for_edit(user_id: str, new_instruction: str, context_user_data: Dict) -> str:
    """Receives the new system instruction and attempts to update the private prompt."""
    if not new_instruction.strip():
        return "新的系统指令不能为空，请重新发送，或使用 /cancel 取消编辑。"

    prompt_id = context_user_data.get('prompt_id_to_edit')
    prompt_name = context_user_data.get('prompt_name_being_edited', '未知角色')

    if not prompt_id:
        log.warning(f"prompt_id_to_edit not found in user_data for user {user_id} during edit.")
        return "抱歉，发生内部错误，无法找到要编辑的角色信息。请重新从 /my_prompts 开始编辑。"

    db = SessionLocal()
    try:
        updated_prompt = update_prompt_instruction(
            db=db,
            prompt_id=prompt_id,
            new_system_instruction=new_instruction,
            user_id=user_id
        )
        if updated_prompt:
            log.info(f"User {user_id} updated private prompt ID {prompt_id} ('{updated_prompt.name}').")
            context_user_data.clear()
            return f"私人角色 **'{updated_prompt.name}'** 的系统指令已成功更新！"
        else:
            # update_prompt_instruction logs errors if it returns None
            return f"更新私人角色 '{prompt_name}' 时发生错误。可能你已无权修改或角色已被删除。"
    except Exception as e:
        log.error(f"Exception updating private prompt ID {prompt_id} for user {user_id}: {e}", exc_info=True)
        return f"更新私人角色 '{prompt_name}' 时发生意外错误，请稍后再试。"
    finally:
        db.close()
        context_user_data.clear()  # Clean up all editing context


# --- Delete Private Prompt Logic ---
async def confirm_delete_private_prompt(user_id: str, prompt_id_to_delete: int) -> str:
    """Deletes a specific private prompt owned by the user."""
    db = SessionLocal()
    try:
        prompt = get_prompt_by_id_and_user(db, prompt_id=prompt_id_to_delete, user_id=user_id)
        if not prompt or prompt.prompt_type != PromptType.PRIVATE or prompt.is_system_default:
            return "无法删除此角色：它可能不存在、不是你的私人角色或是一个不可删除的系统预设角色。"

        prompt_name = prompt.name  # Get name before deletion for the message
        success = delete_prompt(db=db, prompt_id=prompt_id_to_delete, user_id=user_id)

        if success:
            log.info(f"User {user_id} deleted private prompt ID {prompt_id_to_delete} ('{prompt_name}').")
            # Optionally, if this prompt was the active one for the user, reset to default.
            # This logic might be better placed in the handler that calls this, or handled by session auto-creation.
            return f"私人角色 **'{prompt_name}'** 已成功删除。"
        else:
            # delete_prompt logs errors if it returns False
            return f"删除私人角色 '{prompt_name}' 时发生错误。"
    except Exception as e:
        log.error(f"Exception deleting private prompt ID {prompt_id_to_delete} for user {user_id}: {e}", exc_info=True)
        return "删除私人角色时发生意外错误，请稍后再试。"
    finally:
        db.close()


# --- Set Active Private Prompt Logic ---
async def set_active_private_prompt(user_id: str, prompt_id: int) -> str:
    """Sets the active private prompt for the user's private chat by creating a new session."""
    db = SessionLocal()
    try:
        prompt_to_set = get_prompt_by_id_and_user(db, prompt_id=prompt_id, user_id=user_id)

        if not prompt_to_set:
            return "找不到该角色，或你无权使用它。可能已被删除或输入错误。"
        if prompt_to_set.prompt_type != PromptType.PRIVATE:
            return f"无法将角色 **'{prompt_to_set.name}'** 设置为私人聊天角色，因为它不是私人角色类型。"
        # Allow setting system default private prompts
        if not prompt_to_set.is_system_default and prompt_to_set.creator_user_id != user_id:
            # This case should be caught by get_prompt_by_id_and_user, but double check
            return f"你无法设置角色 **'{prompt_to_set.name}'**，因为它不属于你。"

        # Determine base model: prompt's override or global default
        new_base_model = prompt_to_set.base_model_override or \
                         APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash-latest")

        get_or_create_user(db, user_id=user_id)  # Ensure user exists

        new_session = create_new_chat_session(
            db=db,
            telegram_chat_id=user_id,  # For private chat, chat_id is user_id
            telegram_user_id=user_id,
            active_prompt_id=prompt_to_set.id,
            current_base_model=new_base_model
        )

        if new_session:
            log.info(
                f"User {user_id} switched to private prompt '{prompt_to_set.name}' (ID: {prompt_to_set.id}). New session ID {new_session.id} created.")
            return (f"已切换到私人角色: **{prompt_to_set.name}**。\n"
                    "与TA的新对话已经开始！")
        else:
            log.error(
                f"Failed to create new session when user {user_id} tried to set private prompt '{prompt_to_set.name}'.")
            return "切换私人角色时发生错误，未能创建新的对话会话。"
    except Exception as e:
        log.error(f"Error setting active private prompt {prompt_id} for user {user_id}: {e}", exc_info=True)
        if db: db.rollback()
        return "设置私人角色时发生意外错误，请稍后再试。"
    finally:
        if db: db.close()


async def cancel_prompt_operation(user_id: str, context_user_data: Dict) -> str:
    """Generic cancel function for prompt conversation handlers."""
    log.info(f"User {user_id} cancelled prompt operation. Clearing context_user_data: {list(context_user_data.keys())}")
    context_user_data.clear()
    return "操作已取消。"