# gemini-telegram-bot/main.py

import asyncio
from typing import Optional

from telegram import Update, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    Defaults,
    CallbackQueryHandler,
    ConversationHandler,  # Ensure this is imported
    ContextTypes
)
# from telegram.constants import ParseMode # Not used directly for now if defaults handle it

from bot import (
    TELEGRAM_BOT_TOKEN,
    PROMPTS_CONFIG,  # Used by initialize_system_prompts
    PROJECT_ROOT,  # Used by ensure_data_directory
    GEMINI_SETTINGS  # Used by initialize_system_prompts
)
from bot.telegram_adapter.commands import CALLBACK_PREFIX_GROUP_MODE
from bot.utils import log
from bot.database import init_db, SessionLocal
from bot.database.crud import create_prompt as db_create_prompt  # For initialize_system_prompts
# from bot.database.crud import get_system_prompt_by_name # Not directly used in main after this change
from bot.database.models import PromptType  # For initialize_system_prompts
from bot.database import models as db_models  # For initialize_system_prompts
from bot.gemini_service import GeminiService

# Import handlers from the new structure
from bot.telegram_adapter import base as base_handlers
from bot.telegram_adapter import commands as command_handlers  # Still need cancel, my_prompts, upload_prompt (as entry)
from bot.telegram_adapter import callbacks as callback_handlers

# Import states and processing functions from prompt_manager
from bot.message_processing import prompt_manager  # For states and some direct calls
from bot.message_processing import group_chat as group_chat_processor

# --- Helper functions (ensure_data_directory, initialize_system_prompts, post_init) ---
# These should be the same as in your provided main.py
def ensure_data_directory():
    data_dir = PROJECT_ROOT / "data"
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Created data directory: {data_dir}")
        except OSError as e:
            log.error(f"Could not create data directory {data_dir}: {e}")


def initialize_system_prompts():
    db = SessionLocal()
    try:
        log.info("Initializing system prompts from config into database...")
        default_gen_params = GEMINI_SETTINGS.get("default_generation_parameters", {})

        for key, prompt_data_item in PROMPTS_CONFIG.items():
            prompt_name = prompt_data_item.get("name", key)
            prompt_type_str = prompt_data_item.get("prompt_type", "private").upper()
            try:
                prompt_type_enum = PromptType[prompt_type_str]
            except KeyError:
                log.warning(
                    f"Invalid prompt_type '{prompt_type_str}' for '{prompt_name}' in prompts.yml. Defaulting to PRIVATE.")
                prompt_type_enum = PromptType.PRIVATE

            # Check if a system prompt with this name AND type already exists
            query = db.query(db_models.Prompt).filter(
                db_models.Prompt.name == prompt_name,
                db_models.Prompt.is_system_default == True,
                db_models.Prompt.prompt_type == prompt_type_enum  # Check type as well
            )
            already_exists_with_correct_type = query.first()

            if not already_exists_with_correct_type:
                created = db_create_prompt(
                    db=db,
                    name=prompt_name,
                    description=prompt_data_item.get("description"),
                    system_instruction=prompt_data_item.get("system_instruction", ""),
                    prompt_type=prompt_type_enum,  # Use the enum
                    temperature=prompt_data_item.get("temperature", default_gen_params.get("temperature")),
                    top_p=prompt_data_item.get("top_p", default_gen_params.get("top_p")),
                    top_k=prompt_data_item.get("top_k", default_gen_params.get("top_k")),
                    max_output_tokens=prompt_data_item.get("max_output_tokens",
                                                           default_gen_params.get("max_output_tokens")),
                    base_model_override=prompt_data_item.get("base_model_override"),
                    is_system_default=True
                )
                if created:
                    log.info(
                        f"Added system prompt to DB: '{prompt_name}' (Type: {prompt_type_enum.value}, ID: {created.id})")
                else:
                    # crud.create_prompt would log if it failed for a specific reason like name collision for user prompts
                    # For system prompts, this implies a different kind of failure if it returns None.
                    log.error(f"Failed to add system prompt to DB: '{prompt_name}' (CRUD function returned None).")
    except Exception as e:
        log.error(f"Error initializing system prompts: {e}", exc_info=True)
    finally:
        db.close()


async def post_init(application: Application):
    log.info("Running post_init hook...")
    await application.bot.set_my_commands([
        ("start", "🚀 开始/帮助"),
        ("help", "ℹ️ 显示帮助信息"),
        ("my_prompts", "📚 查看和选择私人角色"),
        ("upload_prompt", "✍️ 创建新的私人角色"),  # This command will be an entry point to a ConversationHandler
        # ("/set_prompt", "💡 设置当前私人角色"), # Removed as per user request
        ("cancel", "❌ 取消当前操作"),
    ])
    log.info("Bot commands set.")


# --- Conversation Step Handlers (glue between ConversationHandler and prompt_manager) ---

# For Uploading New Prompt
async def received_instruction_for_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text or not update.effective_user:
        # Should not happen if filters are correct, but good to check
        log.warning("Upload handler: Update, message, text, or user missing.")
        return prompt_manager.UPLOAD_PRIVATE_INSTRUCTION  # Stay in current state

    user_id = str(update.effective_user.id)
    instruction = update.message.text
    if context.user_data is None: context.user_data = {}  # Should be initialized by entry point

    log.debug(f"User {user_id} provided instruction for upload: '{instruction[:50]}...'")
    response_text = await prompt_manager.received_private_instruction_for_upload(user_id, instruction,
                                                                                 context.user_data)
    await update.message.reply_text(response_text)

    # Check if the instruction was accepted and we should move to the next state
    if 'private_instruction_to_upload' in context.user_data:
        return prompt_manager.UPLOAD_PRIVATE_NAME
    else:  # Instruction might have been empty or invalid, stay in current state
        return prompt_manager.UPLOAD_PRIVATE_INSTRUCTION


async def received_name_for_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text or not update.effective_user:
        log.warning("Name handler: Update, message, text, or user missing.")
        return ConversationHandler.END  # Or stay in current state if that's better

    user_id = str(update.effective_user.id)
    name = update.message.text
    if context.user_data is None: context.user_data = {}  # Should exist

    log.debug(f"User {user_id} provided name for upload: '{name}'")
    response_text = await prompt_manager.received_private_prompt_name_and_create(user_id, name, context.user_data)
    await update.message.reply_text(response_text)
    return ConversationHandler.END  # End conversation after attempting to create


# For Editing Existing Prompt (NEW HANDLER)
async def received_new_instruction_for_edit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles receiving the new system instruction during prompt edit."""
    if not update.message or not update.message.text or not update.effective_user:
        log.error("Edit handler: Update, message, text, or user missing.")
        if update.message:  # Try to inform user if possible
            await update.message.reply_text("发生错误，无法处理您的输入。请重试或使用 /cancel。")
        return ConversationHandler.END  # End conversation on error

    user_id = str(update.effective_user.id)
    new_instruction = update.message.text

    if context.user_data is None:  # Should have been initialized by callback returning EDIT_PRIVATE_INSTRUCTION
        log.warning(f"User {user_id} - Edit handler: context.user_data is None. This is unexpected.")
        await update.message.reply_text("编辑会话状态丢失，请重新从 /my_prompts 发起编辑。")
        return ConversationHandler.END

    log.info(
        f"User {user_id} - In received_new_instruction_for_edit_handler with instruction: '{new_instruction[:50]}...'")

    # This function from prompt_manager.py will attempt to update the SQL database
    response_text = await prompt_manager.received_new_instruction_for_edit(user_id, new_instruction, context.user_data)

    await update.message.reply_text(response_text)  # This is your "update finish" message
    return ConversationHandler.END  # End conversation after attempting to edit


async def edit_prompt_entry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """
    Handles the 'edit prompt' button press and acts as an entry point
    for the edit_prompt_conv_handler.
    """
    query = update.callback_query
    if not query or not query.data:
        log.warning("Edit entry callback: Query or query.data is None.")
        return ConversationHandler.END  # Or None

    await query.answer()

    user = update.effective_user
    if not user:
        log.warning("Edit entry callback: No effective_user.")
        if query.message:
            try:
                await query.edit_message_text(text="无法识别用户，请重试。")
            except Exception as e_edit:
                log.error(f"Edit entry callback: Failed to edit message on user recognition failure: {e_edit}")
        return ConversationHandler.END

    user_id = str(user.id)
    callback_data = query.data  # e.g., "pr_edit:123"

    # context.user_data anlegen, falls nicht vorhanden
    if context.user_data is None:
        context.user_data = {}

    chat_id_for_actions: Optional[int] = None
    if query.message and query.message.chat:
        chat_id_for_actions = query.message.chat.id

    try:
        # Extract prompt_id from callback_data (e.g., "pr_edit:PROMPT_ID")
        # This prefix is defined in commands.py or a constants file
        # For this example, let's assume CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT = "pr_edit:"
        if not callback_data.startswith(
                command_handlers.CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT):  # Ensure you have access to this constant
            log.error(f"User {user_id} - Edit entry callback: Unexpected callback_data format: {callback_data}")
            return ConversationHandler.END

        prompt_id_str = callback_data.split(command_handlers.CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT, 1)[1]
        prompt_id_to_edit = int(prompt_id_str)
        log.info(f"User {user_id} - Edit entry callback: Chose to edit private prompt ID {prompt_id_to_edit}.")

        response_text = await prompt_manager.start_edit_private_prompt_flow(user_id, prompt_id_to_edit,
                                                                            context.user_data)

        message_sent_or_edited = False
        try:
            if query.message:
                await query.edit_message_text(text=response_text)
                message_sent_or_edited = True
            elif chat_id_for_actions:
                await context.bot.send_message(chat_id_for_actions, text=response_text)
                message_sent_or_edited = True
            if not message_sent_or_edited:
                log.error(f"User {user_id} - Edit entry callback: Could not send initial edit prompt message.")
        except Exception as e_msg:
            log.error(f"User {user_id} - Edit entry callback: Error sending/editing message: {e_msg}")

        log.debug(
            f"User {user_id} - Edit entry callback: Returning state EDIT_PRIVATE_INSTRUCTION ({prompt_manager.EDIT_PRIVATE_INSTRUCTION}).")
        return prompt_manager.EDIT_PRIVATE_INSTRUCTION

    except (IndexError, ValueError) as e:
        log.error(
            f"User {user_id} - Edit entry callback: Error parsing prompt_id from callback_data '{callback_data}': {e}")
        if query.message:
            try:
                await query.edit_message_text(text="编辑角色时数据错误（ID解析失败），请重试。")
            except Exception:
                pass
        return ConversationHandler.END
    except Exception as e_outer:
        log.error(f"User {user_id} - Edit entry callback: Unexpected error: {e_outer}", exc_info=True)
        if query.message:
            try:
                await query.edit_message_text(text="启动编辑角色流程时发生未知错误。")
            except Exception:
                pass
        return ConversationHandler.END


async def group_mode_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button presses for changing group mode."""
    query = update.callback_query
    if not query or not query.data or not query.message or not query.message.chat:
        log.warning("Group mode callback: critical information missing in query.")
        if query: await query.answer(text="请求处理失败，信息不完整。", show_alert=True)
        return

    await query.answer()  # 快速应答回调

    clicked_user = query.from_user  # 用户对象
    chat = query.message.chat  # 聊天对象

    if not clicked_user:
        log.warning("Group mode callback: query.from_user is None, cannot verify admin status.")
        await query.edit_message_text("无法验证操作用户。")
        return

    # 再次检查点击按钮的用户是否为管理员
    # 注意：is_user_group_admin 需要 Update 对象，但我们这里只有 query。
    # 我们需要直接使用 context.bot.get_chat_member
    is_admin_clicker = False
    try:
        chat_member = await context.bot.get_chat_member(chat_id=chat.id, user_id=clicked_user.id)
        if chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]:
            is_admin_clicker = True
    except Exception as e:
        log.error(
            f"Error re-checking admin status in group_mode_callback for user {clicked_user.id} in chat {chat.id}: {e}")
        # 出错时，为安全起见，假定不是管理员

    if not is_admin_clicker:
        log.info(f"User {clicked_user.id} (non-admin) clicked mode change button in group {chat.id}.")
        # 编辑原消息提示权限不足，或者用 alert 回复
        await query.answer(text="抱歉，只有群管理员才能执行此操作。", show_alert=True)
        # 可以选择不修改原消息，或者修改为提示信息
        # await query.edit_message_text(text=query.message.text + "\n\n操作失败：权限不足。")
        return

    callback_data_str = query.data
    group_id_str = str(chat.id)

    if not callback_data_str.startswith(CALLBACK_PREFIX_GROUP_MODE):
        log.warning(f"Group mode callback: received unexpected data '{callback_data_str}'")
        await query.edit_message_text(text="操作失败：无效的回调数据。")
        return

    new_mode_selected = callback_data_str.split(CALLBACK_PREFIX_GROUP_MODE, 1)[1]

    if new_mode_selected not in ["individual", "shared"]:
        log.warning(f"Group mode callback: received invalid mode '{new_mode_selected}' from data '{callback_data_str}'")
        await query.edit_message_text(text=f"操作失败：无效的模式参数 '{new_mode_selected}'。")
        return

    log.info(
        f"Admin {clicked_user.id} confirmed mode change to '{new_mode_selected}' for group {group_id_str} via button.")

    # 调用核心逻辑处理函数

    response_message_text = await group_chat_processor.set_group_chat_mode(group_id_str, new_mode_selected)

    # 编辑原带有按钮的消息，显示结果
    await query.edit_message_text(text=response_message_text)


async def main_async():
    log.info("Starting bot application...")

    if not TELEGRAM_BOT_TOKEN:
        log.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        return

    ensure_data_directory()
    init_db()  # Initializes tables if they don't exist
    log.info("Database initialized.")

    initialize_system_prompts()  # Loads system prompts from YML to DB
    log.info("System prompts initialized.")

    gemini_service = GeminiService()
    log.info("GeminiService initialized.")

    # Optional: Set default parse mode if you use Markdown extensively
    # defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2)
    # application = Application.builder().token(TELEGRAM_BOT_TOKEN).defaults(defaults).post_init(post_init).build()

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.bot_data["gemini_service"] = gemini_service
    log.info("Telegram Application built and GeminiService stored in bot_data.")

    # --- Define ConversationHandlers ---
    # Handler for UPLOADING a new prompt (initiated by /upload_prompt or button)
    upload_prompt_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("upload_prompt", command_handlers.upload_prompt_command_handler),
        ],
        states={
            prompt_manager.UPLOAD_PRIVATE_INSTRUCTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                               received_instruction_for_upload_handler)
            ],
            prompt_manager.UPLOAD_PRIVATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                               received_name_for_upload_handler)
            ],
        },
        fallbacks=[CommandHandler("cancel", command_handlers.cancel_command_handler)],
        # PTB recommends `per_user=True, per_chat=True` for private chats, which are defaults.
        # `name` can be useful for persistence or debugging.
        # `map_to_state` can be used if entry points directly map to states, but here the command handler returns the first state.
    )

    # Handler for EDITING an existing prompt (initiated by button callback)
    edit_prompt_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                edit_prompt_entry_callback,
                pattern=f"^{command_handlers.CALLBACK_PREFIX_EDIT_PRIVATE_PROMPT}" # Matches "pr_edit:..."
            )
        ],
        states={
            prompt_manager.EDIT_PRIVATE_INSTRUCTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    received_new_instruction_for_edit_handler
                )
            ]
        },
        fallbacks=[CommandHandler("cancel", command_handlers.cancel_command_handler)],
    )

    # --- Register Handlers ---
    # IMPORTANT: ConversationHandlers should typically be added *before* more general message handlers.
    application.add_handler(upload_prompt_conv_handler)  # /upload_prompt
    application.add_handler(edit_prompt_conv_handler)  # button

    # Basic command handlers
    application.add_handler(CommandHandler("start", base_handlers.start_command_handler))
    application.add_handler(CommandHandler("help", base_handlers.help_command_handler))
    # Standalone /cancel command (if not already covered by fallbacks, or for non-conversation cancellation)
    application.add_handler(CommandHandler("cancel", command_handlers.cancel_command_handler))

    # Prompt management commands
    application.add_handler(CommandHandler("my_prompts", command_handlers.my_prompts_command_handler))
    # /upload_prompt is an entry point to upload_prompt_conv_handler, already added.
    # /set_prompt command handler is now removed.

    # Callback Query Handler for /my_prompts buttons (select, edit, delete, create, paginate)
    # This handler (private_prompts_callback_handler) can return states
    # that will be picked up by the ConversationHandlers if those states are defined in them.
    application.add_handler(CallbackQueryHandler(
        callback_handlers.private_prompts_callback_handler,
        # This function will return states like EDIT_PRIVATE_INSTRUCTION or UPLOAD_PRIVATE_INSTRUCTION
        pattern="^pr_"  # Pattern for private prompt callbacks
    ))

    # General Private Message Handler (should be one of the last for private chats)
    # This will only be triggered if no ConversationHandler is currently active for the user.
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        base_handlers.private_message_handler
    ))

    # NEW: General Group Message Handler
    # This will catch any text message in groups/supergroups the bot is in.
    # The handler itself will then check for mentions.
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP),
        base_handlers.group_message_handler # Use the new handler from base.py
    ))

    application.add_handler(CommandHandler("mode", command_handlers.mode_command_handler))
    application.add_handler(
        CommandHandler("set_group_prompt", command_handlers.set_group_prompt_command_handler))
    application.add_handler(CallbackQueryHandler(
        callback_handlers.group_mode_callback_handler, # 新的回调处理函数
        pattern=f"^{CALLBACK_PREFIX_GROUP_MODE}" # 匹配 "grp_mode:" 开头的回调
    ))
    # Error Handler
    application.add_error_handler(base_handlers.error_handler)

    log.info("All bot handlers registered.")
    log.info("Bot is starting to poll for updates...")
    try:
        # For PTB v20+, initialize() and start() are part of Application itself
        await application.initialize()  # Initializes bot, bot_data etc.
        await application.updater.start_polling()  # type: ignore # Start polling (updater is part of Application)
        await application.start()  # Starts the application components
        log.info("Bot is running.")
        # Keep the application running
        while True:
            await asyncio.sleep(3600)  # Or any other mechanism to keep alive
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot shutting down via interrupt...")
    except Exception as e:
        log.critical(f"Bot failed to run: {e}", exc_info=True)
    finally:
        log.info("Attempting to gracefully stop the bot...")
        if application.updater and application.updater.running:  # type: ignore
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        log.info("Bot has been shut down.")


if __name__ == "__main__":
    asyncio.run(main_async())