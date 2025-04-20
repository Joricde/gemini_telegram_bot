import os

import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CallbackContext, CommandHandler,
                          MessageHandler, filters, CallbackQueryHandler)
from telegram.constants import ParseMode, ChatAction
from bot.utils import logger
from bot import PROMPTS, GOOGLE_API_KEY, SAFETY_SETTINGS, BOT_TOKEN

# 加载环境变量
load_dotenv()
genai.configure(api_key=GOOGLE_API_KEY)

# 存储每个用户的模型实例和当前模型名称
user_models: dict[int, genai.ChatSession] = {}
CURRENT_MODEL: dict[int, str] = {}


def set_model(user_id, prompt_name):
    """
    为用户设置模型实例。
    """
    if prompt_name not in PROMPTS:
        raise ValueError(f"Invalid model name: {prompt_name}")

    model_config = PROMPTS[prompt_name]
    user_models[user_id] = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=genai.GenerationConfig(
            temperature=model_config["temperature"],
            top_p=model_config["top_p"],
            top_k=model_config["top_k"],
            max_output_tokens=model_config["max_output_tokens"]
        ),
        safety_settings=SAFETY_SETTINGS,
        system_instruction=model_config["system_instruction"] if len(model_config["system_instruction"])>0 else None,
    ).start_chat()
    CURRENT_MODEL[user_id] = prompt_name
    return user_models[user_id]


def get_model(user_id):
    """获取或创建用户的模型实例"""
    if user_id not in user_models:
        # 默认使用 storyteller 模型
        # logger.debug(list(PROMPTS.keys())[0])
        return set_model(user_id, list(PROMPTS.keys())[0])
    else:
        return user_models[user_id]


async def is_bot_mentioned(update: Update, context: CallbackContext):
    """检查机器人在群组中是否被提及"""
    message = update.message
    if message and message.chat.type == "private":
        return True
    if message.text is not None and ("@" + context.bot.username) in message.text:
        return True
    if message.reply_to_message is not None:
        if message.reply_to_message.from_user.id == context.bot.id:
            return True
    else:
        return False


async def echo(update: Update, context: CallbackContext, message=None):
    """
    处理消息并使用 Gemini 生成回复。
    """
    if not await is_bot_mentioned(update, context):
        return
    _message = message or update.message.text
    # logger.debug(_message)
    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()
    if update.message is not None and update.message.text is not None:
        user_id = update.effective_user.id
        logger.debug(f'user_id:{user_id}')
        session_chat = get_model(user_id)
        response = session_chat.send_message(content=_message, safety_settings=SAFETY_SETTINGS)
        await context.bot.send_message(
            chat_id=update.effective_message.chat_id, text=response.text, parse_mode=ParseMode.MARKDOWN)


async def newchat_command(update: Update, context: CallbackContext) -> None:
    """重置用户的聊天会话"""
    user_id = update.effective_user.id
    if user_id in user_models:
        user_models[user_id] = set_model(user_id, CURRENT_MODEL[user_id])
        await update.message.reply_text("模型已重置。")
    else:
        await update.message.reply_text("你还没有开始对话。")


async def send_model_keyboard(update: Update, context: CallbackContext):
    """创建带有每个可用模型按钮的键盘并将其发送给用户"""
    keyboard = []
    for prompt_key, prompt_value in PROMPTS.items():
        prompt_name = prompt_value["name"]
        keyboard.append(
            [InlineKeyboardButton(prompt_name,
                                  callback_data=prompt_key)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("请选择一个模型：",
                                    reply_markup=reply_markup)


async def handle_model_selection(update: Update,
                                 context: CallbackContext):
    """处理用户从键盘选择的模型"""
    query = update.callback_query
    await query.answer()
    assert query.data in PROMPTS, f"Unknown model: {query.data}"
    prompt_name = query.data
    try:
        user_id = update.effective_user.id
        m = set_model(user_id, prompt_name)
        logger.debug(m)
        CURRENT_MODEL[user_id] = prompt_name
        await query.edit_message_text(f"已切换到模型：{PROMPTS[prompt_name]['name']}")
    except ValueError as e:
        await query.edit_message_text(str(e))


async def error_handler(update,
                        context):
    """记录错误并发送消息给开发者。"""
    logger.error(msg="运行时发生异常:", exc_info=context.error)
    # 可以在这里添加发送消息给开发者的代码，例如：
    # context.bot.send_message(chat_id=update.effective_message.chat_id, text=f"发生错误：{context.error}")


def main():
    token = BOT_TOKEN
    if token is None:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    application = ApplicationBuilder().token(token).build()

    # 添加 /models 命令处理程序
    application.add_handler(CommandHandler("models", send_model_keyboard))
    # 添加模型选择处理程序
    application.add_handler(CallbackQueryHandler(handle_model_selection))

    # 添加消息处理程序
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_handler(CommandHandler("new", newchat_command))

    application.add_error_handler(error_handler)

    logger.info("BOT START FINISH")
    application.run_polling()


if __name__ == "__main__":
    main()
