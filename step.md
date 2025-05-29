## 阶段一：基础架构与核心服务搭建

### 环境与配置

* 创建 **.env** 文件，配置初始的单个 `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `DATABASE_URL`。
* 创建 **config/app_config.yml**，定义数据库路径、默认的 Gemini 参数。
* 将 **config/prompts.json** 转换为 **config/prompts.yml**，并放入几个基础的 prompt 预设。
* 确认 **requirements.txt** 包含所有必要库 (`python-telegram-bot`, `google-generativeai`, `python-dotenv`, `PyYAML`, `SQLAlchemy`)。

### 日志系统

* 在 **bot/utils.py** 中配置日志记录，使其能输出到控制台和 **logs/bot.log** 文件。
* 确保 **logs/** 目录存在（可以在代码中检查并创建）。
* 在 **.gitignore** 中添加 **logs/**。

### 配置加载

* 实现在 **bot/\_\_init\_\_.py** 中加载 **.env** 文件、**app_config.yml** 和 **prompts.yml**，并将配置项作为模块级变量或通过特定函数提供给其他模块使用。

### 数据库模块

* 在 **models.py** 中定义核心数据表结构：**User, Prompt, GroupSetting, ChatSessionState, GroupMessageCache**。
* 在 **crud.py** 中实现对这些表的基础增删改查函数。
* 选择数据库引擎（例如 **SQLite**）。

### Gemini 服务

* 封装与 **Gemini API** 的交互在 **bot/gemini_service.py**。
* 提供函数，接收 `prompt_config` (从数据库加载) 和 `chat_history` (可选)，返回一个配置好的 `genai.GenerativeModel` 实例或直接是 `ChatSession`。
* 提供函数，接收 `ChatSession` 和用户消息，发送请求并返回回复，同时更新 `ChatSession` 的历史。
* 处理 **API key** 配置。

---

## 阶段二：核心私聊功能

### Telegram 适配层与主入口

* 在 **main.py** 中：初始化日志、配置、数据库连接。
    * 创建 `GeminiService` 实例。
    * 创建并配置 `telegram.ext.Application` 实例。
    * 注册来自 **bot/telegram_adapter/** 各模块的处理器。
    * 启动 Bot。
* 在 **bot/telegram_adapter/base.py** 和 **commands.py** 中定义命令和消息处理器。
    * 处理器能访问 `GeminiService` 和数据库 `crud` 函数。

### 私聊逻辑

* 实现在 **bot/message_processing/private_chat.py** 中处理私聊消息的核心逻辑。
* 获取/创建用户的 `ChatSessionState` (基于 `telegram_chat_id`=`user_id`, `telegram_user_id`=`user_id`)，默认使用 `app_config.yml` 中 `default_private_prompt_key` 指定的预设 prompt。
* 实现会话超时逻辑：如果距离上次交互超过1小时，自动创建新的 `ChatSessionState` (沿用之前的 prompt)。
* 从 `ChatSessionState` 恢复 `ChatSession` 历史。
* 调用 `GeminiService` 获取回复。
* 将回复发送给用户。
* 更新并保存 `ChatSessionState` 的历史到数据库。
* 接入到 **bot/telegram_adapter/base.py** 的私聊消息处理器中。

---

## 阶段三：Prompt 管理功能 (私聊)

### Prompt 管理逻辑

* **创建角色 (`/upload_prompt` 或 `/my_prompts` 中的按钮)**:
    * 通过 **ConversationHandler** 引导用户设定 `system_instruction` 和角色名称。
    * 在 **bot/message_processing/prompt_manager.py** 中实现逻辑。
    * 使用 **app_config.yml** 中的默认参数，将新 Prompt (类型为 `PRIVATE`) 存入数据库。
* **查看与管理角色 (`/my_prompts`)**:
    * 在 **bot/telegram_adapter/commands.py** 中实现 `/my_prompts` 命令。
    * 列出用户创建的 `PRIVATE` 类型 Prompts 以及系统预设的 `PRIVATE` 类型 Prompts，分页显示。
    * 提供内联按钮进行以下操作 (通过 **bot/telegram_adapter/callbacks.py** 处理回调):
        * **选择角色**: 激活选定的 Prompt。会结束当前会话（如果存在）并将 `ChatSessionState.active_prompt_id` 更新为选定 Prompt ID，然后开始一个全新的对话。
        * **编辑角色**: 仅限用户创建的 `PRIVATE` Prompts。通过 **ConversationHandler** 引导用户输入新的 `system_instruction` 并更新到数据库。
        * **删除角色**: 仅限用户创建的 `PRIVATE` Prompts。从数据库中删除。
        * **创建新角色按钮**: 跳转到创建角色的对话流程。
* 将这些命令和回调的处理器添加到 **main.py**。

---

## 阶段四：群聊核心功能

### 4.1 群聊消息处理基础与设置

* **创建 `bot/message_processing/group_chat.py`**: 用于存放所有群聊相关的核心业务逻辑。
* **Telegram 群聊消息处理器 (`main.py` & `bot/telegram_adapter/base.py` 或 `group_handlers.py`)**:
    * 在 `main.py` 中注册一个新的 `MessageHandler`，使用 `filters.ChatType.GROUPS` 过滤群聊消息。
    * 此处理器应调用 `bot/telegram_adapter/base.py` (或新的 `group_handlers.py`) 中的一个函数。
    * 该函数需要判断Bot是否被提及 (例如，`@BotName` 在消息文本中，或消息是回复Bot的消息)。
    * 如果Bot被提及，则将 `update` 和 `context` 传递给 `bot/message_processing/group_chat.py` 中的主处理函数，例如 `handle_group_interaction`。
* **`GroupSetting` 初始化与获取 (`group_chat.py`)**:
    * 在 `handle_group_interaction` 中，首先根据 `update.effective_chat.id` (即 `group_id`) 调用 `crud.get_group_setting`。
    * 如果 `GroupSetting` 不存在，则调用 `crud.create_or_update_group_setting` 创建一个默认设置。
        * 默认模式 (`current_mode`) 可以从 `app_config.yml` 的 `default_bot_behavior.group_chat_mode` 读取 (例如，默认为 "individual")。
        * 其他如 `shared_mode_role_prompt_id` 和 `random_reply_enabled` 也可设置初始默认值。
    * 确保为消息发送者调用 `crud.get_or_create_user`。

### 4.2 群聊独立会话模式 (Individual Mode)

* 在 `group_chat.py` 的 `handle_group_interaction` 中：
    * 如果当前群组的 `GroupSetting.current_mode` 为 `"individual"`:
        * `ChatSessionState` 的 `telegram_chat_id` 为群组ID (`group_id`)。
        * `ChatSessionState` 的 `telegram_user_id` 为消息发送者ID (`user_id`)。
        * 调用 `crud.get_active_chat_session_state(db, telegram_chat_id=group_id, telegram_user_id=user_id)` 获取会话。
        * **会话创建/恢复**:
            * 如果会话不存在或已超时（复用私聊的超时逻辑），则创建新会话。
            * 新会话的 `active_prompt_id` 应使用系统默认的私聊prompt (例如，由 `app_config.yml` 中 `default_bot_behavior.default_private_prompt_key` 指定的 `PRIVATE` 类型 Prompt)。
            * 调用 `crud.create_new_chat_session`。
        * **消息处理**:
            * 从用户消息中移除 `@BotName`。
            * 后续交互逻辑（加载历史、调用 `GeminiService`、更新历史）与私聊模式类似，但使用 `(group_id, user_id)` 区分会话。
            * `GeminiService` 调用时不传递 `group_role_payload_instruction`。
        * 将Bot的回复发送到群组。

### 4.3 群聊模式切换 (`/mode` 命令)

* **管理员权限检查工具**:
    * 在 `bot/utils.py` (或 `bot/telegram_adapter/utils.py`) 中创建一个辅助函数 `async def is_user_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool`。
    * 该函数使用 `await context.bot.get_chat_member(chat_id, user_id)` 并检查返回成员的 `status` 是否为 `ChatMember.CREATOR` 或 `ChatMember.ADMINISTRATOR`。
* **命令实现 (`bot/telegram_adapter/commands.py` 和 `group_chat.py`)**:
    * 在 `main.py` 中注册 `CommandHandler("mode", mode_command_handler)`。
    * 在 `commands.py` 中实现 `async def mode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)`。
        * 检查是否在群聊中执行。
        * 调用 `is_user_group_admin` 检查权限。若无权限，则回复提示信息。
        * 从 `context.args` 解析目标模式 (例如 "shared" 或 "individual")。如果参数无效，提示用户。
        * 调用 `group_chat.py` 中的 `async def set_group_chat_mode(group_id: str, new_mode: str) -> str`。
    * 在 `group_chat.py` 中实现 `set_group_chat_mode`:
        * 使用 `crud.create_or_update_group_setting` 更新对应 `group_id` 的 `current_mode`。
        * 返回操作结果的文本消息。
        * **注意**: 切换模式时，可能需要考虑是否要结束/归档当前模式下的会话（例如，从 shared 切到 individual，原来的群共享会话应归档）。

### 4.4 群聊共享会话模式 (Shared Mode) - 提及互动

* 在 `group_chat.py` 的 `handle_group_interaction` 中：
    * 如果当前群组的 `GroupSetting.current_mode` 为 `"shared"` 并且Bot被提及：
        * `ChatSessionState` 的 `telegram_chat_id` 为群组ID (`group_id`)。
        * `ChatSessionState` 的 `telegram_user_id` 为 `None` (或特殊标记，表示是群共享会话)。
        * 调用 `crud.get_active_chat_session_state(db, telegram_chat_id=group_id, telegram_user_id=None)`。
        * **会话创建/恢复**:
            * 如果会话不存在或已超时：
                * 获取 `GroupSetting.shared_mode_role_prompt_id`。
                * 如果未设置，则从 `app_config.yml` 中 `default_bot_behavior.default_group_role_prompt_key` 获取默认的 `GROUP_ROLE_PAYLOAD` 类型的Prompt ID。
                * 确保选中的 Prompt 是 `GROUP_ROLE_PAYLOAD` 类型。
                * 调用 `crud.create_new_chat_session` (传入 `telegram_user_id=None`)。
            * **消息处理**:
                * 从用户消息中移除 `@BotName`。
                * **构建复合Prompt**:
                    * `group_role_payload_instruction` = 已选定 `GROUP_ROLE_PAYLOAD` 类型 Prompt 的 `system_instruction`。
                    * `gemini_service.start_chat_session` 时，除了传递此 `group_role_payload_instruction`，`GeminiService` 内部会使用 `GROUP_CHAT_SETTINGS.default_system_headers_template` 来组合最终的系统指令。
                * `GeminiService` 实际发送给模型的用户消息可能需要包含用户名，例如通过模板格式化为 "`username`: `message_text`"，具体取决于 `default_system_headers_template` 中的 `INPUT_FORMAT`。
            * 将Bot的回复发送到群组。

### 4.5 设置群聊共享角色 (`/set_group_prompt` 命令)

* **命令实现 (`bot/telegram_adapter/commands.py` 和 `group_chat.py`)**:
    * 在 `main.py` 中注册 `CommandHandler("set_group_prompt", set_group_prompt_command_handler)`。
    * 在 `commands.py` 中实现 `async def set_group_prompt_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)`。
        * 检查群聊和管理员权限。
        * 从 `context.args` 获取 `prompt_name_or_id`。
        * **Prompt查找与验证**:
            * 允许管理员从系统预设的 `GROUP_ROLE_PAYLOAD` 类型 Prompts 中选择。
            * 通过 `crud.get_system_prompt_by_name` 或 `crud.get_prompt_by_id` 查找。
            * 验证找到的 Prompt 确实是 `GROUP_ROLE_PAYLOAD` 类型。
        * 调用 `group_chat.py` 中的 `async def set_group_shared_role_prompt(group_id: str, prompt_id: int) -> str`。
    * 在 `group_chat.py` 中实现 `set_group_shared_role_prompt`:
        * 使用 `crud.create_or_update_group_setting` 更新 `shared_mode_role_prompt_id`。
        * **重要**: 更新群角色后，应归档当前群组的共享会话 (`crud.archive_previous_active_sessions(db, telegram_chat_id=group_id, telegram_user_id=None)`), 以便下次互动时使用新的角色开始一个干净的会话。
        * 返回操作结果消息。

---

## 阶段五：随机插嘴功能

### 消息缓存

* 确保 **bot/database/crud.py** 中有 `add_message_to_cache` 和 `get_recent_messages_from_cache` 函数。

### 随机插嘴逻辑

* 修改群聊消息处理器 (**`main.py` 中注册的，指向 `bot/telegram_adapter/base.py` 或 `group_handlers.py` 的函数**):
    * 使其监听所有群消息（不仅仅是 `@Bot` 或回复Bot）。这意味着移除之前专门判断是否提及Bot的逻辑分支，或者在该分支不满足时执行以下逻辑。
* 每收到一条非机器人自己发送的群消息：
    * 调用 `crud.add_message_to_cache` 将其存入 `GroupMessageCache` (包含 `group_id`, `message_id`, `user_id`, `text`, `timestamp`)。
* 在 `group_chat.py` 的 `handle_group_interaction` (或者一个专门的 `handle_random_reply` 函数，由主群聊处理器在Bot未被直接提及时调用)：
    * 检查当前群组 `GroupSetting` 是否为 `shared` 模式且 `random_reply_enabled` 为 `True`。
    * **概率触发逻辑**:
        * 例如，从 `app_config.yml` 的 `group_chat_settings.random_reply_parameters` 读取 `listen_message_count` 和 `base_probability_p_denominator`。
        * 当缓存中的消息数量达到 `listen_message_count` 时，才开始计算概率。
        * 以 `1 / base_probability_p_denominator` 的概率触发。可以使用 `random.randrange(0, base_probability_p_denominator) == 0`。
    * **如果触发**:
        * 调用 `crud.get_recent_messages_from_cache` 获取最近N条消息 (N 也可以配置)。
        * 将这些消息格式化为适合 `GeminiService` 的上下文文本 (例如，每条消息 "`username`: `text`"，按时间顺序排列)。
        * 使用当前群共享模式的 `GROUP_ROLE_PAYLOAD` Prompt (如阶段 4.4 所述构建复合Prompt) 调用 `GeminiService`。注意，这里 `GeminiService` 的 `send_message` 的输入是整个上下文，而不是单条用户消息。可能需要 `GeminiService` 有一个类似 `generate_reply_from_context` 的方法，或者 `start_chat_session` 后，将格式化的上下文作为历史或首条用户消息。
        * 将回复发送到群组 (不需要 `@`任何人)。

---

## 阶段六：测试、优化与部署准备

* **全面测试**：测试所有功能，包括私聊、群聊各种模式、Prompt 管理、错误处理。
* **代码优化与重构**：清理代码，提高可读性和效率。
* **错误处理与日志完善**：确保关键操作都有恰当的错误捕获和日志记录。
* **文档**：编写 **README.md**，包含项目介绍、配置方法、运行指南。

---

## 阶段七：会话管理与格式调整 (回顾与确认)

### 总体目标 (已部分实现或融入其他阶段)
从每个用户更新单个、长期存在的聊天会话，转变为在提示切换或会话不活跃超过一小时时创建新的、独立的聊天会话。

### I. 数据库模型调整 (bot/database/models.py)
* **`ChatSessionState.is_active`**: 已实现并使用。
* **主键与唯一性**: `id` 为主键，通过 `is_active=True` 保证每个 `(telegram_chat_id, telegram_user_id)` 组合只有一个活跃会话的逻辑已在 `crud` 和业务逻辑中实现。

### II. CRUD 操作修改 (bot/database/crud.py)
* `get_active_chat_session_state`: 已实现，获取 `is_active=True` 的会话。
* `archive_previous_active_sessions`: 已实现。
* `create_new_chat_session`: 已实现，会先归档旧的。
* `update_chat_history`: 已实现。

### III. 业务逻辑调整 (私聊部分已完成)
* **`bot/message_processing/private_chat.py`**:
    * 会话超时逻辑和新会话创建（因超时或首次交互）已实现。
* **`bot/message_processing/prompt_manager.py`**:
    * 切换Prompt时 (通过 `/my_prompts` 按钮) 创建新会话已实现 (`set_active_private_prompt` 调用 `create_new_chat_session`)。
    * **阶段四将把类似的会话管理逻辑（如切换群模式或群角色时新建会话）引入群聊。**

### IV. 解析模式调整 (通用)
* **确认ParseMode**: 检查所有 `reply_text`, `edit_message_text`, `send_message` 调用。
    * 如果需要 Markdown，应明确指定 `parse_mode=ParseMode.MARKDOWN`。
    * `main.py` 中目前没有设置全局 `Defaults(parse_mode=...)`。可以考虑添加，或在每个发送富文本消息的地方单独指定。
    * 当前 `base.py` 和 `commands.py` 中的回复大多未使用Markdown。 `prompt_manager.py` 返回的文本中使用了 `**` 加粗，如果这些要渲染，则发送时需要指定Markdown。

### V. 时间处理
* 确保所有 Python `datetime` 对象都是时区感知的 (推荐 UTC)。
* 数据库中的 `last_interaction_at` 列使用 `DateTime(timezone=True)` 和 `onupdate=func.now()`。 SQLite 的 `func.now()` 通常生成 UTC 时间戳字符串，SQLAlchemy 能处理。

**结论**: 阶段七大部分核心会话管理机制已针对私聊实现。阶段四会将其扩展到群聊。解析模式是需要全项目检查和统一的点。

---

## 后续扩展到多 Bot "身份"的考虑 (在上述单 Bot 实现稳固后)

* 修改 **main.py** 和 **bot/telegram\_adapter/**：使其能够读取 **.env** 中的多个 `TELEGRAM_BOT_TOKENS`。
* 为每个 Token 创建一个 `Application` 实例。
* 确保 **handlers.py** 在处理 `Update` 时，能识别出是哪个 Bot Token 接收到的事件 (通过 `update.message.bot.id`)，并将此 `bot_id` 传递给 `message_processing` 模块。
* 修改 **bot/message_processing/**：各业务逻辑模块 (如 **group_chat.py**) 在执行操作时，可以根据传入的 `bot_id` 来应用不同的行为。
* 修改配置 (**config/app_config.yml, config/prompts.yml**):可以为不同的 `bot_id` 定义特定的默认配置或特色 Prompts。
* 数据库调整 (可能需要):`GroupSetting`、`ChatSessionState` 等表可能需要增加 `bot_id` 字段来区分不同 Bot "身份" 的设置和状态。