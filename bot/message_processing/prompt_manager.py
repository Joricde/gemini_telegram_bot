# bot/message_processing/prompt_manager.py

from sqlalchemy.orm import Session
from typing import Dict, Optional

from bot import APP_CONFIG
from bot.database import SessionLocal
from bot.database import models as db_models
from bot.database.models import PromptType
from bot.database.crud import (
    create_prompt,
    get_prompt_by_id_and_user,
    get_prompt_by_name_and_user,
    update_prompt_instruction, # Ensure this is imported
    delete_prompt,
    create_new_chat_session,
    get_or_create_user
)
from bot.utils import log

# --- Constants for ConversationHandler states ---
UPLOAD_PRIVATE_INSTRUCTION, UPLOAD_PRIVATE_NAME = range(2)
EDIT_PRIVATE_INSTRUCTION = 3 # This state is for when bot is waiting for new instruction text


def _get_default_gen_params() -> dict:
    return APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})


async def start_upload_private_prompt_flow(user_id: str, context_user_data: Dict) -> str:
    context_user_data.clear()
    db = SessionLocal()
    try:
        get_or_create_user(db, user_id=user_id)
    finally:
        db.close()
    return (
        "好的，我们来创建一个新的私人角色。\n\n"
        "请发送你想要定义的角色的**系统指令 (System Instruction)**。\n"
        "例如：`你是一个乐于助人的助手，总是以积极的口吻回答问题。`\n\n"
        "输入 /cancel 可以随时取消创建。"
    )


async def received_private_instruction_for_upload(user_id: str, instruction: str, context_user_data: Dict) -> str:
    if not instruction.strip():
        return "系统指令不能为空，请重新发送你的系统指令，或使用 /cancel 取消。"
    context_user_data['private_instruction_to_upload'] = instruction
    return (
        "指令已收到！现在请为这个私人角色设定一个**唯一的名称**。\n"
        "例如：`我的私人助理`\n\n"
        "输入 /cancel 可以随时取消。"
    )


async def received_private_prompt_name_and_create(user_id: str, name: str, context_user_data: Dict) -> str:
    name = name.strip()
    if not name:
        return "角色名称不能为空，请重新发送名称，或使用 /cancel 取消。"
    if len(name) > 50:
        return "角色名称过长（最多50个字符），请换一个短一点的名称，或使用 /cancel 取消。"

    system_instruction = context_user_data.get('private_instruction_to_upload')
    if not system_instruction:
        log.warning(f"System instruction for upload not found in user_data for user {user_id}.")
        return "抱歉，发生内部错误，找不到之前输入的系统指令。请使用 /upload_prompt 重新开始。"

    db = SessionLocal()
    try:
        existing_prompt = get_prompt_by_name_and_user(db, name=name, user_id=user_id, prompt_type=PromptType.PRIVATE)
        if existing_prompt:
            return f"你已经有一个名为 '{name}' 的私人角色了。请换一个名称，或使用 /my_prompts 查看并管理你的角色。"

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
            is_system_default=False
        )
        if new_prompt:
            log.info(f"User {user_id} created new private prompt '{name}' (ID: {new_prompt.id}).")
            context_user_data.clear()
            return (f"私人角色 **'{name}'** 创建成功！🎉\n"
                    f"你可以使用 /my_prompts 命令来查看和选择它。")
        else:
            return "创建私人角色时发生错误。可能是名称已被使用或数据库问题。请稍后再试或更改名称。"
    except Exception as e:
        log.error(f"Exception creating private prompt '{name}' for user {user_id}: {e}", exc_info=True)
        return "创建私人角色时发生意外错误，请稍后再试。"
    finally:
        db.close()
        context_user_data.pop('private_instruction_to_upload', None)


async def start_edit_private_prompt_flow(user_id: str, prompt_id_to_edit: int, context_user_data: Dict) -> str:
    """Initiates the editing process for a specific private prompt."""
    context_user_data.clear() # Clear previous conversation data
    db = SessionLocal()
    try:
        # Ensure user exists, not strictly necessary here if prompt check is robust, but good practice
        get_or_create_user(db, user_id=user_id)

        prompt = get_prompt_by_id_and_user(db, prompt_id=prompt_id_to_edit, user_id=user_id)

        if not prompt:
            return "无法找到该角色，或者你无权编辑它。"
        if prompt.is_system_default:
            return "系统预设角色不可编辑。"
        if prompt.prompt_type != PromptType.PRIVATE:
            return "该角色不是私人聊天角色，无法在此处编辑。"

        context_user_data['prompt_id_to_edit'] = prompt_id_to_edit
        context_user_data['prompt_name_being_edited'] = prompt.name # Store for user feedback

        original_instruction_snippet = (prompt.system_instruction[:100] + '...') if len(
            prompt.system_instruction) > 100 else prompt.system_instruction

        return (
            f"你正在编辑私人角色：{prompt.name}。\n"
            f"当前的系统指令为：\n`{original_instruction_snippet}`\n\n"
            f"现在，请直接发送新的系统指令。原来的指令将被完全替换。\n\n"
            f"输入 /cancel 可以随时取消编辑。"
        )
    finally:
        db.close()


async def received_new_instruction_for_edit(user_id: str, new_instruction: str, context_user_data: Dict) -> str:
    """Receives the new system instruction and attempts to update the private prompt."""
    if not new_instruction.strip():
        # User might send an empty message. Prompt them again or ask to cancel.
        return "新的系统指令不能为空。请重新发送你的指令，或者输入 /cancel 取消编辑。"

    prompt_id = context_user_data.get('prompt_id_to_edit')
    prompt_name = context_user_data.get('prompt_name_being_edited', '当前角色') # Fallback name

    if prompt_id is None: # Should not happen if flow is correct
        log.error(f"User {user_id}: 'prompt_id_to_edit' not found in user_data during edit process.")
        context_user_data.clear() # Clear potentially corrupt state
        return "抱歉，编辑过程中发生内部错误（无法找到角色ID）。请尝试重新从 /my_prompts 发起编辑，或使用 /cancel。"

    db = SessionLocal()
    try:
        updated_prompt = update_prompt_instruction(
            db=db,
            prompt_id=prompt_id,
            new_system_instruction=new_instruction,
            user_id=user_id # Pass user_id for permission check within update_prompt_instruction
        )
        if updated_prompt:
            log.info(f"User {user_id} successfully updated instruction for prompt ID {prompt_id} ('{updated_prompt.name}').")
            context_user_data.clear()
            return f"私人角色 '{updated_prompt.name}' 的系统指令已成功更新！"
        else:
            # update_prompt_instruction should ideally return None if not found or not permitted
            log.warning(f"User {user_id}: Failed to update prompt ID {prompt_id}. update_prompt_instruction returned None.")
            # It's possible the prompt was deleted by another process, or permissions changed.
            # CRUD function should handle specific error logging.
            context_user_data.clear()
            return f"更新私人角色 '{prompt_name}' 时发生错误。可能该角色已被删除，或你不再拥有修改权限。请使用 /my_prompts 查看最新列表。"
    except Exception as e:
        log.error(f"User {user_id}: Exception while updating prompt ID {prompt_id}: {e}", exc_info=True)
        db.rollback()
        context_user_data.clear()
        return f"更新私人角色 '{prompt_name}' 时发生意外的服务器内部错误，请稍后再试。"
    finally:
        db.close()
        # Ensure context_user_data is cleared regardless of success/failure if the operation concluded
        # context_user_data.pop('prompt_id_to_edit', None)
        # context_user_data.pop('prompt_name_being_edited', None)
        # Clearing all is usually safer for a completed or failed conversation step.

async def confirm_delete_private_prompt(user_id: str, prompt_id_to_delete: int) -> str:
    db = SessionLocal()
    try:
        prompt = get_prompt_by_id_and_user(db, prompt_id=prompt_id_to_delete, user_id=user_id)
        if not prompt or prompt.prompt_type != PromptType.PRIVATE or prompt.is_system_default:
            return "无法删除此角色：它可能不存在、不是你的私人角色或是一个不可删除的系统预设角色。"

        prompt_name = prompt.name
        success = delete_prompt(db=db, prompt_id=prompt_id_to_delete, user_id=user_id)

        if success:
            log.info(f"User {user_id} deleted private prompt ID {prompt_id_to_delete} ('{prompt_name}').")
            return f"私人角色 '{prompt_name}' 已成功删除。"
        else:
            return f"删除私人角色 '{prompt_name}' 时发生错误。"
    except Exception as e:
        log.error(f"Exception deleting private prompt ID {prompt_id_to_delete} for user {user_id}: {e}", exc_info=True)
        return "删除私人角色时发生意外错误，请稍后再试。"
    finally:
        db.close()


async def set_active_private_prompt(user_id: str, prompt_id: int) -> str:
    db = SessionLocal()
    try:
        prompt_to_set = get_prompt_by_id_and_user(db, prompt_id=prompt_id, user_id=user_id)

        if not prompt_to_set:
            return "找不到该角色，或你无权使用它。可能已被删除或输入错误。"
        if prompt_to_set.prompt_type != PromptType.PRIVATE:
            return f"无法将角色 '{prompt_to_set.name}' 设置为私人聊天角色，因为它不是私人角色类型。"
        if not prompt_to_set.is_system_default and prompt_to_set.creator_user_id != user_id:
            return f"你无法设置角色 '{prompt_to_set.name}'，因为它不属于你。"

        new_base_model = prompt_to_set.base_model_override or \
                         APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash-latest")

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
                f"User {user_id} switched to private prompt '{prompt_to_set.name}' (ID: {prompt_to_set.id}). New session ID {new_session.id} created.")
            return (f"已切换到私人角色: {prompt_to_set.name}。\n"
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
    log.info(f"User {user_id} cancelled prompt operation. Clearing context_user_data: {list(context_user_data.keys())}")
    context_user_data.clear()
    return "操作已取消。"