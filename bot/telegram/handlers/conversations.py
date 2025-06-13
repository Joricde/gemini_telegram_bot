# bot/telegram/handlers/conversations.py
import re
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.database import crud
from bot.services.prompt_service import PromptService
from bot.core.logging import logger
from .callbacks import show_prompt_management_menu

# --- 1. 定义对话状态 (Define Conversation States) ---
# 使用数字常量来表示对话的不同阶段，清晰明了
AWAITING_PROMPT_TEXT = 1


async def add_prompt_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Starts the conversation to add a new prompt. This is the entry point.
    It asks the user for the new prompt's content.
    """
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            text="好的，请发送你想要添加的新角色设定。\n\n"
                 "请遵循以下格式：\n\n"
                 "Title: [你的角色标题]\n\n"
                 "[你的角色详细描述]\n\n"
                 "随时可以输入 /cancel 来取消操作。"
        )

    # 告诉 ConversationHandler，我们现在进入了 AWAITING_PROMPT_TEXT 状态
    return AWAITING_PROMPT_TEXT


async def received_prompt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the user's message containing the new prompt text.
    It parses, validates, and saves the prompt.
    """
    user_id = update.effective_user.id
    message_text = update.message.text

    # --- 2. 解析用户输入 (Parse User Input) ---
    title_match = re.search(r"^Title:\s*(.*)", message_text, re.IGNORECASE)
    # 找到第一个空行，之后的所有内容都视为 prompt_text
    parts = re.split(r'\n\s*\n', message_text, 1)

    if not title_match or len(parts) < 2:
        await update.message.reply_text(
            "格式似乎不对哦。请确保你的消息包含 'Title: ...' 和一个空行来分隔标题和描述。\n\n"
            "例如：\n"
            "Title: 莎士比亚\n\n"
            "你是一位剧作家，语言风格复古而华丽。\n\n"
            "请重试，或输入 /cancel 取消。"
        )
        # 保持在当前状态，等待用户重新输入
        return AWAITING_PROMPT_TEXT

    title = title_match.group(1).strip()
    prompt_text = parts[1].strip()

    if not title or not prompt_text:
        await update.message.reply_text(
            "标题和描述都不能为空，请重新发送。或输入 /cancel 取消。"
        )
        return AWAITING_PROMPT_TEXT

    # --- 3. 保存到数据库 (Save to Database) ---
    try:
        prompt_service: PromptService = context.bot_data["prompt_service"]
        prompt_service.create_new_prompt(user_id=user_id, title=title, text=prompt_text)
        logger.info(f"User {user_id} successfully created prompt '{title}'")
        await update.message.reply_text(
            f"✅ 角色 '{title}' 添加成功！现在所有用户都可以使用它了。"
        )
    except Exception as e:
        logger.error(f"Failed to create prompt by user {user_id}. Error: {e}", exc_info=True)
        await update.message.reply_text("抱歉，创建角色时发生错误，请稍后再试。")

    # --- 4. 结束对话 (End Conversation) ---
    # 显示更新后的 prompt 列表
    if update.callback_query:
        await show_prompt_management_menu(update, context)

    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the entire conversation process.
    """
    user = update.effective_user
    logger.info(f"User {user.id} canceled the conversation.")
    await update.message.reply_text(
        "好的，操作已取消。"
    )
    # 告诉 ConversationHandler 对话已结束
    return ConversationHandler.END
