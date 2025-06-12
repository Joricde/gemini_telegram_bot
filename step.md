## 阶段一：基础架构与核心服务搭建

### 环境与配置

* 创建 **.env** 文件，配置初始的单个 `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `DATABASE_URL`。
* 创建 **config/app_config.yml**，定义数据库路径、默认的 Gemini 参数。
* 将 **config/prompts.json** 转换为 **config/prompts.yml**，并放入几个基础的 prompt 预设。
* 确认 **requirements.txt** 包含所有必要库 (`python-telegram-bot`, `google-generativeai`, `python-dotenv`, `PyYAML`, `SQLAlchemy` 或 `sqlite3`)。

### 日志系统

* 在 **bot/utils.py** 中配置日志记录，使其能输出到控制台和 **logs/bot.log** 文件。
* 确保 **logs/** 目录存在（可以在代码中检查并创建）。
* 在 **.gitignore** 中添加 **logs/**。

### 配置加载

* 实现在 **bot/\_\_init\_\_.py** 中加载 **.env** 文件、**app_config.yml** 和 **prompts.yml**，并将配置项作为模块级变量或通过特定函数提供给其他模块使用。

### 数据库模块

* 在 **models.py** 中定义核心数据表结构：**User, Prompt, GroupSetting, ChatSessionState, GroupMessageCache** (初期可以先简化，例如 `ChatSessionState` 只包含 `chat_id`, `prompt_id`, `history`)。
* 在 **crud.py** 中实现对这些表的基础增删改查函数。初期可以先实现 **User** 和 **Prompt** 的基本操作。
* 选择数据库引擎（例如 **SQLite** 开始，方便快捷）。

### Gemini 服务

* 封装与 **Gemini API** 的交互。
* 提供函数，接收 `prompt_config` (从数据库或配置文件加载) 和 `chat_history` (可选)，返回一个配置好的 `genai.GenerativeModel` 实例或直接是 `ChatSession`。
* 提供函数，接收 `ChatSession` 和用户消息，发送请求并返回回复，同时更新 `ChatSession` 的历史。
* 处理 **API key** 配置。

---

## 阶段二：核心私聊功能

### Telegram 适配层与主入口

* 在 **main.py** 中：初始化日志、配置、数据库连接。
    * 创建 `GeminiService` 实例。
    * 创建并配置 `telegram.ext.Application` 实例 (使用 **.env** 中的单个 Token)。
    * 注册来自 **handlers.py** 的处理器。
    * 启动 Bot (`application.run_polling()`)。
* 在 **handlers.py** 中：定义一个简单的 **/start** 命令处理器和消息处理器。
    * 这些处理器需要能访问 `GeminiService` 和数据库 `crud` 函数 (可以通过 `context.bot_data` 传递实例，或者使用依赖注入的方式)。

### 私聊逻辑

* 实现在 **bot/message_processing/private_chat.py** 中处理私聊消息的核心逻辑：当收到用户消息时，检查用户是否存在于数据库，不存在则创建。
* 获取/创建用户的 `ChatSessionState` (初期可以为每个用户默认使用 **prompts.yml** 中的一个预设 prompt)。
* 从 `ChatSessionState` 恢复 `ChatSession` 历史。
* 调用 `GeminiService` 获取回复。
* 将回复发送给用户。
* 更新并保存 `ChatSessionState` 的历史到数据库。
* 将此逻辑接入到 **handlers.py** 的私聊消息处理器中。

---

## 阶段三：Prompt 管理功能

### Prompt 管理逻辑

* 实现在 **bot/message_processing/prompt_manager.py** 中实现 **/upload\_prompt** 命令逻辑：
    * 引导用户设定 `system_instruction`。
    * 提示用户为 Prompt 命名。
    * 使用默认参数或 **app_config.yml** 中的参数（也就是说用户最少只需要设定 prompt的name 以及 system_instruction 即可写入SQL中，其他参数皆使用默认），将新 Prompt 存入数据库 (`Prompt` 表)。
* 实现 **/my\_prompts** 命令，列出目前SQL库内拥有的 Prompts。
* 实现 **/set\_prompt <prompt_name_or_id>** 命令，允许用户在私聊中切换当前对话使用的 Prompt (更新对应 `ChatSessionState` 中的 `active_prompt_id`，并可能需要重置会话历史或提示用户)。
* 将这些命令的处理器添加到 **handlers.py**。

---

## 阶段四：群聊核心功能

### 群聊直接互动与模式基础

* 实现在 **bot/message_processing/group_chat.py** 中处理群内 `@Bot` 或回复 Bot 消息的逻辑。
* **模式切换准备**：在 `GroupSetting` 表中记录群的模式（默认为 `individual`）。
* **独立会话模式 (初期重点)**：当用户在群内 `@Bot` 时，为 `group_id + user_id` 创建或获取独立的 `ChatSessionState`。
    * 后续交互逻辑类似私聊，但会话与特定群组内的特定用户绑定。
* 将此逻辑接入到 **handlers.py** 的群聊消息处理器中。

### 群聊模式切换命令

* 在 **group_chat.py** 实现 **/mode <shared|individual>** 命令逻辑 (需要权限检查，例如仅群管理员)。
* 该命令会更新数据库中对应群组的 `GroupSetting`。
* 在 **handlers.py** 注册此命令。

### 群聊共享会话模式

* 当群聊模式为 `shared` 时：所有对 Bot 的直接互动都使用群级别的 `ChatSessionState` (基于 `group_id`，可能还需要一个默认的 `shared_mode_prompt_id`)。
* 实现 **/set\_group\_prompt <prompt_name_or_id>** 命令，允许管理员为共享模式设置 Prompt。

---

## 阶段五：随机插嘴功能

### 消息缓存

* 确保 **crud.py** 中有添加消息到缓存和从缓存获取最近 N 条消息的函数。

### 随机插嘴逻辑

* 修改群聊消息处理器 (**handlers.py**)，使其监听所有群消息（不仅仅是`@Bot`）。
* 每收到一条群消息，就将其存入 `GroupMessageCache`。
* 如果当前群组模式为 `shared` 且随机插嘴功能开启 (`GroupSetting`)：
    * 实现概率触发逻辑 (例如，每收到一条消息，就有 `1/P` 的概率触发，`P` 可以根据缓存中的消息数量动态调整)。
    * 如果触发，从缓存获取最近 N 条消息。
    * 将消息格式化为上下文文本。
    * 使用群共享模式的 Prompt 调用 `GeminiService` 获取回复。
    * 将回复发送到群组。

---

## 阶段六：测试、优化与部署准备

* **全面测试**：测试所有功能，包括私聊、群聊各种模式、Prompt 管理、错误处理。
* **代码优化与重构**：清理代码，提高可读性和效率。
* **错误处理与日志完善**：确保关键操作都有恰当的错误捕获和日志记录。
* **文档**：编写 **README.md**，包含项目介绍、配置方法、运行指南。

---

## 阶段七：会话管理与格式调整 (从 dev_steps.md 整合)

### 总体目标
从每个用户更新单个、长期存在的聊天会话，转变为在提示切换或会话不活跃超过一小时时创建新的、独立的聊天会话。这确保对话更具限定性，并且历史记录不会无限增长或长时间暂停后变得不相关。

### I. 数据库模型调整 (bot/database/models.py)

**修改 ChatSessionState 表**：
* **添加 `is_active` 列**：
    * `is_active = Column(Boolean, default=True, nullable=False, index=True)`
    * **目的**：此标志将表示特定 `(telegram_chat_id, telegram_user_id)` 组合的当前活跃会话。当为此组合创建新会话时（由于提示切换或超时），该相同组合的任何先前会话的 `is_active` 标志将被设置为 `False`。
* **审查主键和唯一性**：
    * `id`（自增主键）将唯一标识每个会话记录。
    * 活跃会话的 `(telegram_chat_id, telegram_user_id)` 不再有隐式唯一约束。相反，应用程序逻辑将确保在任何给定时间此对只有一个会话处于活跃状态。同一对可以存在多个非活跃会话，表示历史对话。

### II. CRUD 操作修改 (bot/database/crud.py)

* **修改 `get_chat_session_state(db: Session, telegram_chat_id: str, telegram_user_id: str | None = None)`**：
    * **变更**：此函数现在必须检索单个活跃会话。
    * **逻辑**：
        * 按 `telegram_chat_id`、`telegram_user_id` 和 `is_active == True` 过滤。
        * 如果发现多个活跃会话（这将表示数据不一致），记录错误并返回 `last_interaction_at` 最新的会话。理想情况下，这种情况应由其他逻辑阻止。
        * 返回单个 `models.ChatSessionState` 对象或 `None`。
* **修改 `create_or_update_chat_session_state` (考虑重命名，例如 `manage_chat_session_state` 或使用不同的函数)**：
    * 此函数的作用发生显著变化。它不再仅仅是更新现有记录或在不存在时创建记录。它现在涉及归档旧会话和创建新会话。更清晰的方法可能是拥有：
        * **`archive_previous_active_sessions(db: Session, telegram_chat_id: str, telegram_user_id: str | None = None)` (新辅助函数)**：
            * **逻辑**：
                * 查找给定 `telegram_chat_id` 和 `telegram_user_id` 且 `is_active == True` 的所有 `ChatSessionState` 记录。
                * 对于每个找到的会话，设置 `is_active = False`。
                * 提交更改。
        * **`create_new_chat_session(db: Session, telegram_chat_id: str, active_prompt_id: int, current_base_model: str, telegram_user_id: str | None = None)` (新函数或改编函数)**：
            * **逻辑**：
                * 首先，为给定的 `telegram_chat_id` 和 `telegram_user_id` 调用 `archive_previous_active_sessions`。
                * 创建新的 `models.ChatSessionState` 实例，包含：
                    * 提供的 `telegram_chat_id`、`telegram_user_id`、`active_prompt_id`、`current_base_model`。
                    * `gemini_chat_history = None`（或 `json.dumps([])`），因为这是新会话。
                    * `is_active = True`。
                * 添加到会话，提交，刷新，并返回新的 `ChatSessionState` 对象。
        * **`update_chat_history(db: Session, session_id: int, new_gemini_chat_history: list)` (新函数或改编函数)**：
            * **逻辑**：
                * 通过其唯一 `id` 获取 `ChatSessionState`。
                * 如果找到且 `is_active == True`：
                    * 将 `new_gemini_chat_history` 序列化为 JSON。
                    * 更新 `gemini_chat_history` 字段。
                    * `last_interaction_at` 字段应由于 `onupdate=func.now()` 自动更新。
                    * 提交并刷新。
                * 如果未找到或不活跃，记录警告/错误。

### III. 业务逻辑调整

* **`bot/message_processing/private_chat.py` (handle_private_message)**：
    * **会话检索**：
        * 调用修改后的 `get_chat_session_state` 以获取当前活跃会话。
    * **超时逻辑和会话创建**：
        * 如果检索到 `active_session`：
            * 获取当前 UTC 时间。
            * 将 `current_time` 与 `active_session.last_interaction_at` 进行比较。
            * 如果 `(current_time - active_session.last_interaction_at).total_seconds() > 3600`（1 小时）：
                * 日志记录：“用户 X 的会话已超时。正在创建新会话。”
                * 使用来自超时会话的 `active_prompt_id` 和 `current_base_model` 调用 `create_new_chat_session` 以开始一个使用相同提示的新会话。
                * `active_session` 变量现在应该指向这个新会话。
        * 如果未检索到 `active_session`（例如，首次交互，或之前的会话已归档，这是触发新会话的原因）：
            * 日志记录：“未找到用户 X 的活跃会话。正在创建新的默认会话。”
            * 确定默认提示（例如，来自 `APP_CONFIG` 或回退）。
            * 确定默认基础模型。
            * 使用这些默认值调用 `create_new_chat_session`。
            * `active_session` 变量现在应该指向这个新会话。
    * **历史管理**：
        * `gemini_service.start_chat_session` 的 `deserialized_history` 将来自 `active_session.gemini_chat_history`。如果这是一个全新的会话，此历史将为空/null。
    * **保存交互**：
        * 在成功的 Gemini 交互后，获取 `updated_serializable_history`。
        * 使用 `active_session.id` 和 `updated_serializable_history` 调用 `update_chat_history`。
* **`bot/message_processing/prompt_manager.py` (set_active_prompt)**：
    * **提示切换时的会话创建**：
        * 验证 `prompt_to_set` 后：
            * 日志记录：“用户 X 正在切换提示到 Y。正在创建新会话。”
            * 根据 `prompt_to_set` 或全局默认值确定 `new_base_model`。
            * 使用 `telegram_user_id`、`prompt_to_set.id` 和 `new_base_model` 调用 `create_new_chat_session`。
            * 回复消息应清楚说明已开始使用新角色的新对话。
    * **`list_my_prompts`**：
        * 要显示“（当前激活）”标记，它现在应该使用 `get_chat_session_state` 获取当前活跃会话，然后比较其 `active_prompt_id`。

### IV. 解析模式调整 (通用)

* **`bot/telegram_adapter/handlers.py`**：
    * 将所有 `reply_markdown_v2` 调用更改为 `reply_markdown` 或 `reply_text`。
    * 如果使用 `reply_markdown`，请确保使用的 Markdown 语法与 Telegram 的标准 Markdown 兼容（比 V2 宽松）。
* **`main.py`**：
    * 将 `defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2)` 更改为 `defaults = Defaults(parse_mode=ParseMode.MARKDOWN)`。如果默认首选纯文本，则从 `Defaults` 中删除 `parse_mode`，并且仅在需要富文本的处理器中指定 `parse_mode=ParseMode.MARKDOWN`。

### V. 时间处理

* 确保所有 Python `datetime` 对象都是时区感知的（推荐 UTC）。使用 `datetime.now(timezone.utc)`。
* 数据库中的 `last_interaction_at` 列使用 `DateTime(timezone=True)` 和 `onupdate=func.now()`。确认 `func.now()` 在你特定的数据库（本例中为 SQLite，根据 `bot/__init__.py` 中的 `DATABASE_URL` 默认值）生成时区感知的时间戳或与 Python 的 UTC `datetimes` 一致可比较的时间戳。对于 SQLite，`func.now()` 通常以字符串格式 `'YYYY-MM-DD HH:MM:SS'` 生成 UTC 时间戳。SQLAlchemy 处理转换。

### 用户消息流摘要

1.  用户发送消息。
2.  调用 `private_message_handler`。
3.  `handle_private_message` 逻辑：
    a. `get_or_create_user`。
    b. `get_chat_session_state`（获取 `is_active=True` 的会话）。
    c. 如果会话存在：
        i. 检查 `last_interaction_at` 与 `now(timezone.utc)`。
        ii. 如果 `> 1` 小时：调用 `create_new_chat_session`（归档旧会话，创建使用相同提示的新会话）。`current_session` 变为这个新会话。
    d. 否则（没有活跃会话）：调用 `create_new_chat_session`（归档任何残留的旧会话，创建使用默认提示的新会话）。`current_session` 变为这个新会话。
    e. 从 `current_session.gemini_chat_history` 加载历史记录（如果是新会话则为空）。
    f. 与 `GeminiService` 交互。
    g. 调用 `update_chat_history` 将新历史记录保存到 `current_session.id`。

这种方法确保每个新的“对话上下文”（超时或提示切换后）都从一个全新的历史记录开始，并通过 `ChatSessionState` 中的新行进行管理，同时保留旧的上下文但将其标记为非活跃。

---

## 后续扩展到多 Bot "身份"的考虑 (在上述单 Bot 实现稳固后)

* 修改 **main.py** 和 **bot/telegram\_adapter/**：使其能够读取 **.env** 中的多个 `TELEGRAM_BOT_TOKENS`。
* 为每个 Token 创建一个 `Application` 实例。
* 确保 **handlers.py** 在处理 `Update` 时，能识别出是哪个 Bot Token 接收到的事件 (通过 `update.message.bot.id`)，并将此 `bot_id` 传递给 `message_processing` 模块。
* 修改 **bot/message_processing/**：各业务逻辑模块 (如 **group_chat.py**) 在执行操作时，可以根据传入的 `bot_id` 来应用不同的行为（例如，不同的 Bot "身份" 在同一群组的共享模式下使用不同的 Prompt 或有不同的随机插嘴概率）。
* 修改配置 (**config/app_config.yml, config/prompts.yml**):可以为不同的 `bot_id` 定义特定的默认配置或特色 Prompts。
* 数据库调整 (可能需要):`GroupSetting`、`ChatSessionState` 等表可能需要增加 `bot_id` 字段来区分不同 Bot "身份" 的设置和状态。