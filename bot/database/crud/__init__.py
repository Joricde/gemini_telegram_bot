# bot/database/crud/__init__.py

# --- 从 user_crud.py 导入 ---
from .user_crud import get_or_create_user

# --- 从 session_crud.py 导入 ---
from .session_crud import (
    get_or_create_session,
    get_session,
    update_session,
    reset_session,
    set_active_prompt_key_for_session  # <--- 关键：添加这一行
)

# --- 从 prompt_crud.py 导入 ---
from .prompt_crud import (
    create_user_prompt,
    get_all_db_prompts, # 我们现在主要用这个
    get_db_prompt_by_id, # 这个也需要被 service 使用
    delete_prompt,
    # 下面这两个可以删掉了，因为它们的功能已经被取代或修复
    # get_user_prompts,
    # set_active_prompt_for_user,
    # higet_all_db_prompts, # 这是个拼写错误，也删掉
)