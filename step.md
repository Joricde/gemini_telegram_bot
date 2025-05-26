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

## 后续扩展到多 Bot "身份"的考虑 (在上述单 Bot 实现稳固后)

* 修改 **main.py** 和 **bot/telegram_adapter/**：使其能够读取 **.env** 中的多个 `TELEGRAM_BOT_TOKENS`。
* 为每个 Token 创建一个 `Application` 实例。
* 确保 **handlers.py** 在处理 `Update` 时，能识别出是哪个 Bot Token 接收到的事件 (通过 `update.message.bot.id`)，并将此 `bot_id` 传递给 `message_processing` 模块。
* 修改 **bot/message_processing/**：各业务逻辑模块 (如 **group_chat.py**) 在执行操作时，可以根据传入的 `bot_id` 来应用不同的行为（例如，不同的 Bot "身份" 在同一群组的共享模式下使用不同的 Prompt 或有不同的随机插嘴概率）。
* 修改配置 (**config/app_config.yml, config/prompts.yml**):可以为不同的 `bot_id` 定义特定的默认配置或特色 Prompts。
* 数据库调整 (可能需要):`GroupSetting`、`ChatSessionState` 等表可能需要增加 `bot_id` 字段来区分不同 Bot "身份" 的设置和状态。