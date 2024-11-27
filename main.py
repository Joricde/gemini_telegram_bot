from bot.utils import logger
import os
from dotenv import load_dotenv

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot.handlers import (
    start,
    echo,
    set_model,
    get_models,
    error_handler,
)

def main():
    """
    启动 Telegram Bot。
    """
    # 获取 Telegram Bot Token
    # 创建 Application
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    application = ApplicationBuilder().token(token).build()

    # 添加命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))  # 使用 /start 命令作为帮助
    application.add_handler(CommandHandler("set_model", set_model))
    application.add_handler(CommandHandler("get_models", get_models))
    # 添加消息处理器
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # 添加错误处理器
    application.add_error_handler(error_handler)

    # 启动 Bot
    application.run_polling()

if __name__ == "__main__":
    main()