import os
from utils import logger
from telegram import Update, ForceReply
from telegram.ext import ContextTypes, MessageHandler, filters

from bot.gemini import (
    get_available_models,
    set_current_model,
    get_current_model,
    generate_text,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    发送欢迎消息并显示帮助信息。
    """
    user = update.effective_user
    await update.message.reply_html(
        rf"您好 {user.mention_html()} ! 我是一个 Telegram Bot，"
        r"可以使用 Gemini 模型生成文本。"
        r"您可以向我发送任何消息，我会尽力回复您。",
        reply_markup=ForceReply(selective=True),
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理消息并使用 Gemini 生成回复。
    """
    if update.message is not None and update.message.text is not None:
        prompt = update.message.text
        model = get_current_model(update.effective_user.id)
        logger.info(f"使用模型 {model} 生成回复...")
        response = generate_text(model, prompt, update.effective_user.id)
        await update.message.reply_text(response)

async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    设置用户当前使用的模型。
    """
    user = update.effective_user
    if context.args:
        model_id = context.args[0]
        available_models = get_available_models()
        if model_id in available_models:
            set_current_model(user.id, model_id)
            await update.message.reply_text(f"已将您的模型设置为 {model_id}")
        else:
            await update.message.reply_text(
                f"无效的模型 ID。可用的模型：{', '.join(available_models)}"
            )
    else:
        current_model = get_current_model(user.id)
        await update.message.reply_text(
            f"您当前的模型是 {current_model}。"
            f"可用的模型：{', '.join(get_available_models())}"
        )

async def get_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    获取可用的模型列表。
    """
    await update.message.reply_text(
        f"可用的模型：{', '.join(get_available_models())}"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    记录错误并发送消息给开发者。
    """
    logger.error(msg="处理更新时发生异常:", exc_info=context.error)
    # 可以在这里添加发送消息给开发者的代码