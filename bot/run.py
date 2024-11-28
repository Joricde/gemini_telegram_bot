import os
from dotenv import load_dotenv

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot import BOT_TOKEN
from bot.handlers import (
    start,
    echo,
    set_model,
    get_models,
    error_handler,
)

def run():
    token = BOT_TOKEN
    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))  # 使用 /start 命令作为帮助
    application.add_handler(CommandHandler("set_model", set_model))
    application.add_handler(CommandHandler("get_models", get_models))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.add_error_handler(error_handler)

    application.run_polling()
