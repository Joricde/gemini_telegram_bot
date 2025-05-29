# gemini-telegram-bot/bot/telegram_adapter/base.py

from typing import Optional

from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.constants import ChatAction, ParseMode

from bot.message_processing.group_chat import handle_group_interaction
from bot.utils import log
from bot.database import SessionLocal
from bot.database.crud import get_or_create_user
from bot.message_processing.private_chat import handle_private_message
from bot.gemini_service import GeminiService


# bot/telegram_adapter/base.py

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and basic instructions when the /start command is issued."""
    user = update.effective_user
    # ... (user fetching logic remains the same) ...
    db = SessionLocal()
    try:
        db_user = get_or_create_user(
            db,
            user_id=str(user.id), # type: ignore
            username=user.username, # type: ignore
            first_name=user.first_name, # type: ignore
            last_name=user.last_name # type: ignore
        )
        user_display_name = db_user.first_name or db_user.username or "用户"
    finally:
        db.close()

    log.info(f"User {user.id} ({user.username}) started bot with /start") # type: ignore

    welcome_message = (
        f"你好，{user_display_name}! 👋\n\n"
        f"我是一个由 Gemini 驱动的智能聊天机器人。\n"
        f"你可以直接向我发送消息开始对话。\n\n"
        f"**常用命令**:\n"
        f"`/start` 或 `/help` - 显示此帮助信息\n"
        f"`/my_prompts` - 查看、选择、编辑或删除你的私人角色\n" # Updated this line
        f"`/upload_prompt` - 创建一个新的自定义私人角色\n"
        f"`/cancel` - 在创建或编辑角色等操作中途取消\n"
        f"`/mode <individual|shared>` - (仅群管理员) 切换群聊互动模式\n"
        f"`/set_group_prompt <角色ID或名称>` - (仅群管理员) 设置群聊共享模式下的机器人角色\n" # Added /set_group_prompt
    )
    if update.message:
        await update.message.reply_text(text=welcome_message)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends help message; currently aliases to start_command_handler."""
    await start_command_handler(update, context)


async def private_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles direct private text messages from users that are not part of an ongoing conversation.
    """
    message = update.message
    user = update.effective_user

    if not message or not message.text or not user:
        log.debug("Ignoring empty message, non-text message, or message without user in private_message_handler.")
        return

    if message.chat.type != "private":
        log.debug(f"Ignoring message from non-private chat ({message.chat.type}) in private_message_handler.")
        return

    # Check if a conversation is active for this user (PTB does this implicitly if this handler is added after ConvHandlers)
    # If this handler is intended to catch messages ONLY when no conversation is active,
    # its placement in application.add_handler matters, or more explicit checks are needed.
    # For now, assume it's for general private messages.

    log.info(f"General private message from {user.id} ({user.username}): '{message.text[:50]}...'")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    gemini_service_instance = context.bot_data.get("gemini_service")
    if not isinstance(gemini_service_instance, GeminiService):
        log.error("GeminiService not found or not of correct type in bot_data.")
        if message: await message.reply_text("抱歉，AI服务当前不可用，请稍后再试。")
        return

    try:
        response_text = await handle_private_message(
            user_id=str(user.id),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            message_text=message.text,
            gemini_service=gemini_service_instance
        )
    except Exception as e:
        log.error(f"Unhandled exception in private_message_handler calling handle_private_message: {e}", exc_info=True)
        response_text = "处理您的消息时发生了非常意外的错误。"

    if response_text:
        try:
            if message: await message.reply_text(response_text)
        except Exception as e:
            log.error(f"Error sending reply to user {user.id}: {e}", exc_info=True)
            log.error(f"Error sending message {user.id}: {response_text}", exc_info=True)
            try:
                if message: await message.reply_text(response_text)
            except Exception as e_plain:
                log.error(f"Error sending reply as plain text to user {user.id}: {e_plain}", exc_info=True)
    elif message:  # Only reply if message object exists
        log.warning(f"handle_private_message returned None or empty string for user {user.id}. Sending generic error.")
        await message.reply_text("抱歉，我无法处理您的请求或AI未能生成有效回复。")


async def is_bot_mentioned(message: Message, bot_username: str) -> bool:
    """Checks if the bot is mentioned in the message or if it's a reply to the bot."""
    if not message or not message.text:  # Check if message and message.text exist
        return False

    # 1. Direct @mention
    if f"@{bot_username}" in message.text:
        return True

    # 2. Reply to bot's message
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.username == bot_username:
        return True

    return False


async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages from group chats.
    Passes to group_interaction_handler if the bot is mentioned or replied to.
    """
    if not update.message or not update.effective_chat or not context.bot.username:
        # update.effective_chat might be None for some updates, but message.chat should exist for MessageUpdates
        log.debug("Group message handler: Update, message, effective_chat, or bot username missing.")
        return

    # Ensure it's a group chat (though the filter in main.py should handle this)
    if update.effective_chat.type not in ["group", "supergroup"]:
        log.debug(f"Message not from a group or supergroup: {update.effective_chat.type}")
        return

    # For now, we only care about text messages that mention the bot.
    # Later, for random replies, this check will be different.
    # TODO: Ensure context.bot.username is available. It should be after application initialization.

    bot_username = context.bot.username
    if not bot_username:
        log.error("Cannot determine bot username in group_message_handler. context.bot.username is None.")
        return

    if await is_bot_mentioned(update.message, bot_username):
        log.info(
            f"Bot was mentioned in group {update.effective_chat.id} by user {update.message.from_user.id if update.message.from_user else 'UnknownUser'}.")
        # Pass to the specific group interaction logic
        await handle_group_interaction(update, context)
    else:
        # Bot was not mentioned. For now, do nothing.
        # Later, this is where random reply logic or message caching for context might go.
        # log.debug(f"Bot not mentioned in group {update.effective_chat.id}. Message ignored for direct interaction.")
        pass


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates and send a user-friendly message."""
    log.error(msg="Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="抱歉，处理您的请求时发生了一个内部错误。我们已记录此问题。"
            )
        except Exception as e:
            log.error(f"Failed to send error message to user after an error: {e}")


from bot.database.crud import get_or_create_user, add_message_to_cache # Import add_message_to_cache
from bot.message_processing.group_chat import handle_group_interaction, handle_potential_random_reply # Import new handler


async def group_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages from group chats.
    Caches all messages. Passes to group_interaction_handler if bot is mentioned.
    Otherwise, considers for random reply.
    """
    if not update.message or not update.effective_chat or not context.bot or not context.bot.username:
        log.debug("Group message handler: Update, message, effective_chat, or bot username missing.")
        return

    # Ignore messages from the bot itself to prevent loops and self-caching
    if update.message.from_user and update.message.from_user.is_bot and update.message.from_user.username == context.bot.username:
        return

    if update.effective_chat.type not in ["group", "supergroup"]:
        log.debug(f"Message not from a group or supergroup: {update.effective_chat.type}")
        return

    # --- Cache the message ---
    # We should cache even if it's a text message or other types, but random reply will likely only use text.
    # For simplicity, let's assume we are mainly interested in text messages for now for caching context.
    # If you want to cache all message types (stickers, photos for context later), adjust accordingly.
    if update.message.text and update.message.from_user:  # Only cache text messages from users for now
        db = SessionLocal()
        try:
            user_for_cache = get_or_create_user(
                db,
                user_id=str(update.message.from_user.id),
                username=update.message.from_user.username,
                first_name=update.message.from_user.first_name,
                last_name=update.message.from_user.last_name
            )
            # Ensure group_setting exists for FK constraint in GroupMessageCache if your DB enforces it strictly
            # (Though GroupMessageCache.group_id is FK to GroupSetting.group_id)
            # group_setting_crud.get_or_create_group_setting(db, str(update.effective_chat.id)) # Already done in handle_group_interaction / handle_potential_random_reply

            cached_msg = add_message_to_cache(
                db=db,
                group_id=str(update.effective_chat.id),
                message_id=str(update.message.message_id),
                user_id=str(update.message.from_user.id),  # Storing who sent the message
                username=update.message.from_user.username,  # Storing username
                text=update.message.text,
                timestamp=update.message.date or datetime.datetime.now(datetime.timezone.utc)
                # message.date is already timezone-aware UTC
            )
            if cached_msg:
                log.debug(f"Message {cached_msg.id} cached for group {cached_msg.group_id}")
            else:
                log.warning(f"Failed to cache message from group {update.effective_chat.id}")
        except Exception as e:
            log.error(f"Error caching message for group {update.effective_chat.id}: {e}", exc_info=True)
        finally:
            db.close()

    bot_username = context.bot.username  # Should be available
    if not bot_username:
        log.error("Cannot determine bot username in group_message_handler (for mention check).")
        return

    if await is_bot_mentioned(update.message, bot_username):
        log.info(f"Bot was mentioned in group {update.effective_chat.id}. Passing to handle_group_interaction.")
        await handle_group_interaction(update, context)
    else:
        # Bot was not mentioned. Consider for random reply.
        log.debug(f"Bot not mentioned in group {update.effective_chat.id}. Passing to handle_potential_random_reply.")
        await handle_potential_random_reply(update, context)

