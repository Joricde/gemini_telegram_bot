import logging
import os

import google.generativeai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackContext, CommandHandler
import google.generativeai as genai

from bot.utils import logger

# 配置 Gemini API 客户端
dotenv_path = os.path.join(os.path.dirname(__file__), '../.env')

# 加载 .env 文件
load_dotenv(dotenv_path=dotenv_path)
# logger.info(dotenv_path)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
# Create the model
# generation_config = google.generativeai.GenerationConfig(
# temperature= 2,
#   top_p= 1,
#   top_k= 40,
#   max_output_tokens=512,
#   response_mime_type="text/plain",)
# model = genai.GenerativeModel(
#     model_name="gemini-1.5-flash",
#     generation_config=generation_config,
#     system_instruction="请你严格扮演以下角色：记住你的设定(你是一个百年一遇的金发碧眼美少女,对自己的容貌也非常有自信)\n\n角色设定：莉莉丝·怀特\n\n姓名： 莉莉丝·怀特 (Lilith White)\n\n年龄： 18岁\n\n外貌：  一头如阳光般耀眼的金发，配上一双清澈湛蓝的眼眸。精致的五官，白皙的肌肤，加上高挑纤细的身材，百年一遇的美少女。\n\n性格：\n\n毒舌吐槽役: 莉莉丝拥有与生俱来的毒舌天赋，仿佛世间万物皆可吐槽。她总能敏锐地捕捉到周围的槽点。\n\n百科全书式智慧: 她拥有惊人的知识储备，上至天文地理，下至人文历史，几乎无所不知。丰富的知识储备不仅为她的吐槽提供了强大的火力支持，也让她在任何场合都能侃侃而谈，令人叹服。\n\n冷静的观察者: 尽管莉莉丝的吐槽火力凶猛，但她始终保持着冷静的头脑。她善于观察和分析，能够迅速看穿事物的本质，并做出精准的判断。\n\n\n特长：\n\n逻辑推理:  莉莉丝拥有强大的逻辑思维能力，能够快速分析问题、找出关键信息，并进行严密的推理。她总能一针见血地指出问题所在，并给出合理的解决方案。\n\n网络冲浪大师: 莉莉丝是网络世界的原住民，精通各种网络语言和流行文化。她活跃于各大社交平台，对各种梗和段子了如指掌，并能将其巧妙地融入到自己的吐槽中，使得她的语言更具活力和感染力。\n\n说话风格：\n 莉莉丝的吐槽可谓炉火纯青，她不仅能用词精准、逻辑清晰，并以犀利、幽默、夸张的语言进行无情嘲讽或者使用辛辣的讽刺、一针见血的指出本质亦或者使用包含隐喻的金句。让她的吐槽充满杀伤力。无论是面对朋友、敌人还是陌生人，她都能找到对方的弱点，并以精准的吐槽给予致命一击。对话内容极其凝练简洁",
# )

user_models: dict[int, genai.GenerativeModel] = {}

def get_model(user_id):
    """获取或创建用户的模型实例"""
    if user_id not in user_models:
        user_models[user_id] = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=google.generativeai.GenerationConfig(temperature= 2,
                                                                   top_p= 1,
                                                                   top_k= 40,
                                                                   max_output_tokens=512,
                                                                   response_mime_type="text/plain",),
            system_instruction="你是金发碧眼的美少女大小姐,你的说话风格是毒舌,智慧,冷静.非常擅长以<凝练简洁,暗喻,幽默,夸张,一针见血>地指出事物的根本."

        )
    return user_models[user_id]

async def is_bot_mentioned(update: Update, context: CallbackContext):
    message = update.message
    if message.chat.type == "private":
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
    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()
    # logger.info("context: %s ", context.bot)
    # logger.info("update: %s ", update)
    if update.message is not None and update.message.text is not None:
        user_id = update.effective_user.id
        # logger.info(user_id)
        session_chat = get_model(user_id).start_chat()
        # logger.info(type(session_chat))
        response = session_chat.send_message(_message)
        # logging.info("response: %s ", response)
        await context.bot.send_message(chat_id=update.effective_message.chat_id, text=response.text)

async def reset_chat(update: Update, context: CallbackContext):
    pass

async def newchat_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id in user_models:
        del user_models[user_id]
        await update.message.reply_text("模型已重置。")
    else:
        await update.message.reply_text("你还没有开始对话。")


def main():
    token=os.getenv("BOT_TOKEN")
    if token is None:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")


    application = ApplicationBuilder().token(token).build()

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_handler(CommandHandler("new", newchat_command ))
    logger.info("BOT START FINISH")
    application.run_polling()


if __name__ == "__main__":
    # 配置日志
    main()