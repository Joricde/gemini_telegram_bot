# 可扩展的多“身份”Telegram 聊天机器人项目文档

## 1. 项目概述

本项目旨在开发一个具备高度可扩展性的 Telegram 聊天机器人平台，支持私聊和多种群聊互动模式。项目的架构设计将着重于解耦和模块化，以便未来可以轻松接入更多的 Telegram Bot "身份"，这些“身份”可以共享核心服务，但在用户感知上表现为独立的机器人，可能拥有不同的预设性格或负责特定的交互任务。

## 2. 核心功能 (通过初始 Bot "身份"提供)

* **私聊模式:**
    * 用户可以与 Bot 进行一对一的私密对话。
    * 用户可以为自己的私聊会话选择或上传自定义的 Prompt (System Instruction)。
    * 每个用户的私聊会话历史独立保存。
* **群聊模式:**
    * **直接互动:** 在群组中，用户可以通过 `@Bot` 或回复 Bot 的消息来与其互动。
    * **模式切换 (群管理员指令):**
        * **共享会话模式 (`/mode shared`):**
            * Bot 在该群组中表现为一个统一的个体，所有群成员与之互动时共享同一个 Gemini `ChatSession`。
            * 群管理员可以为此共享会话设置一个特定的 Prompt。
            * 在此模式下，Bot 会监听群内最近的对话。
            * Bot 会根据预设概率对群内对话进行**随机插嘴**，回复时会结合上下文。
        * **独立会话模式 (`/mode individual`):**
            * 当用户在群内 `@Bot` 或回复 Bot 时，每个用户都将拥有一个与 Bot 的独立 `ChatSession`，对话历史独立。
            * 在此模式下，Bot **不再进行主动的随机插嘴**。
    * **Prompt 管理:**
        * 用户可以通过指令 (`/upload_prompt`) 上传自定义的 `system_instruction` 来创建新的 Prompt 预设。
        * 新上传的 Prompt 的其他 Gemini 参数将采用系统预设的默认值。
        * 用户可以管理和选择自己创建或收藏的 Prompt (`/my_prompts`, `/set_prompt`)。

## 3. 项目结构 (设计时考虑多 Bot "身份"扩展性)

```text
gemini-telegram-bot/
├── .env                      # 存储 API Tokens, 数据库连接信息, 代理设置等
├── main.py                   # 项目主入口，初始化服务并启动 Bot 实例管理器
├── requirements.txt          # Python 依赖库
├── config/                   # 应用配置目录
│   ├── app_config.yml        # 应用级配置 (数据库路径, 默认行为, 随机回复参数等)
│   └── prompts.yml           # 预设的 Prompt (System Instructions, Gemini 参数等)
└── bot_service/              # 核心 Bot 服务与逻辑
    ├── __init__.py
    ├── database/             # 数据库模块
    │   ├── __init__.py
    │   ├── models.py         # SQLAlchemy 模型定义
    │   └── crud.py           # 数据库增删改查操作
    ├── gemini_service.py     # 封装 Gemini API 交互, 管理 ChatSession
    ├── message_processing/   # 消息处理与业务逻辑
    │   ├── __init__.py
    │   ├── private_chat.py   # 私聊逻辑
    │   ├── group_chat.py     # 群聊逻辑 (包括模式切换、随机插嘴)
    │   └── prompt_manager.py # Prompt 上传与管理逻辑
    ├── telegram_adapter/     # Telegram Bot 实例管理与适配层
    │   ├── __init__.py
    │   ├── instance_manager.py # 管理一个或多个 Telegram Bot Application 实例
    │   └── handlers.py         # 通用的 Telegram 事件处理器，分发到具体业务逻辑
    └── utils.py              # 通用工具函数 (日志配置等)

```

## 4. 核心模块详解

### 4.1. 配置文件

* `.env`:
    * **TELEGRAM\_BOT\_TOKENS**: 一个逗号分隔的字符串，包含一个或多个 Telegram Bot Token。初期只有一个。例如: `"your_bot_token_1,your_bot_token_2"`
    * **GEMINI\_API\_KEY**: Google Gemini API 密钥。
    * **DATABASE\_URL**: 数据库连接字符串。
    * **HTTP\_PROXY, HTTPS\_PROXY** (可选)。
* `config/app_config.yml`:
    * 数据库相关配置。
    * 默认群聊模式。
    * 随机插嘴的参数（监听消息数、基础概率等）。
    * 上传 Prompt 时的默认 Gemini 参数。
    * 为不同 Bot "身份" (Token) 指定默认 Prompt 或行为的配置节 (未来扩展用)。
* `config/prompts.yml`:
    * 包含多个预设的 Prompt 定义，每个定义包含 `name`, `system_instruction`, Gemini 参数等。
    * 可以有一个特殊的字段，如 `assign_to_bot_id` 或 `tags`，用于未来将特定 Prompts 与特定 Bot "身份" 关联。

### 4.2. bot\_service/database/

* `models.py`:
    * **用户表 (User)**: `user_id` (Telegram ID, PK), `username`, `first_name`, `last_name`.
    * **Prompts 表 (Prompt)**: `id` (PK), `creator_user_id` (FK), `name`, `system_instruction`, `model_name`, `temperature`, `top_p`, `top_k`, `max_output_tokens`, `is_system_default` (bool).
    * **群组设置表 (GroupSetting)**: `group_id` (PK), `default_mode` ("shared" 或 "individual"), `shared_mode_prompt_id` (FK), `random_reply_enabled` (bool).
    * **会话状态表 (ChatSessionState)**: `id` (PK), `telegram_chat_id` (私聊ID或群聊ID), `telegram_user_id` (在群聊独立模式下区分用户), `active_prompt_id` (FK), `gemini_chat_history` (TEXT/JSON), `last_interaction_at`.
    * **群聊消息缓存表 (GroupMessageCache)**: `id` (PK), `group_id`, `message_id`, `user_id`, `username`, `text`, `timestamp`.
* `crud.py`: 包含对上述模型进行增删改查的函数。

### 4.3. bot\_service/gemini\_service.py

* 与之前设计类似，封装 Gemini API 交互，管理 `genai.ChatSession` 的创建、历史恢复、消息发送。
* 会从 `database.crud` 获取 Prompt 配置来初始化 `GenerativeModel`。

### 4.4. bot\_service/message\_processing/

* `private_chat.py`:
    * 处理所有私聊相关的逻辑。
    * 调用 `gemini_service` 进行对话。
    * 通过 `database.crud` 存取用户私聊的 `ChatSessionState`。
* `group_chat.py`:
    * 处理所有群聊相关的逻辑。
    * 管理群聊模式切换 (`GroupSetting`)。
    * **共享模式**: 使用群级别（或指定Bot身份的群级别）的 `ChatSessionState`。实现随机插嘴，从 `GroupMessageCache` 获取上下文，调用 `gemini_service`。
    * **独立模式**: 为每个在群内与Bot互动的用户管理独立的 `ChatSessionState`。
* `prompt_manager.py`:
    * 处理用户上传、查询、选择 Prompt 的逻辑。
    * 与 `database.crud` 交互来存储和检索 `Prompt` 对象。

### 4.5. bot\_service/telegram\_adapter/

* `instance_manager.py`:
    * **核心**：能够读取 `.env` 中的 `TELEGRAM_BOT_TOKENS`。
    * 为每个 Token 创建并管理一个独立的 `telegram.ext.Application` 实例。
    * 将所有 Bot 实例的事件统一接入到 `handlers.py`。
    * **关键设计点**： 当 `handlers.py` 中的处理器被调用时，它需要知道是哪个 Bot "身份" (哪个 Token) 接收到的事件，以便后续逻辑（如选择特定 Prompt，或记录行为）可以区分。`CallbackContext` 可以用来传递这个信息。
* `handlers.py`:
    * 包含通用的 `CommandHandler` 和 `MessageHandler`。
    * 这些处理器会接收来自所有 Bot "身份" 的 `Update` 和 `Context`。
    * 根据 `update.message.bot.id` (或通过 context 传递的 Bot "身份" 标识符) 和消息类型，将请求路由到 `message_processing` 中的相应模块 (e.g., `private_chat.py`, `group_chat.py`)。
    * 例如，一个 `@bot` 的群聊消息，`handlers.py` 会先确定是哪个 `bot_id` 被 `@`，然后调用 `group_chat.py` 的相应函数，并传入这个 `bot_id` 以便 `group_chat.py` 可以为这个 "身份" 应用特定的逻辑或 Prompt。

### 4.6. main.py

* 初始化日志、配置、数据库。
* 创建 `gemini_service` 实例。
* 创建 `message_processing` 各模块的实例 (如果它们是类)。
* 创建 `telegram_adapter.InstanceManager` 实例，并启动所有 Bot "身份"。

---

## 5. 设计关键点 (为了解耦和扩展)

* **核心服务与 Telegram 适配层分离**: `gemini_service` 和 `message_processing` 中的业务逻辑不直接依赖于 `python-telegram-bot` 的具体实现，而是通过 `telegram_adapter` 来桥接。
* **Bot "身份" 识别**: 在消息处理流程中，能够清晰地识别出当前是哪个 Bot Token (哪个 "身份") 在响应。这可以通过 `update.message.bot.id` 在 `handlers.py` 中获取，并作为参数传递给业务逻辑层。
* **配置驱动行为**: 不同 Bot "身份" 的特定行为（例如默认 Prompt、是否启用某功能）可以通过 `config/app_config.yml` 中与 Bot Token ID 关联的配置节来定义。业务逻辑层会根据当前的 Bot "身份" ID 去查找和应用这些配置。
* **数据库设计**:
    * `GroupSetting` 可以增加一个 `bot_identifier` 字段，如果不同的 Bot "身份" 在同一个群里可以有不同的设置。
    * `ChatSessionState` 可以增加 `bot_identifier` 字段，如果同一个用户与不同 Bot "身份" 的对话历史需要区分。
    * `Prompt` 表可以增加 `default_for_bot_ids` 列表字段，指定某些 Prompt 是某些 Bot "身份" 的默认或特色 Prompt。

---

## 6. 初期实现 (单一 Bot "身份")

在初期，`TELEGRAM_BOT_TOKENS` 将只包含一个 Token。`InstanceManager` 将只管理一个 `Application` 实例。但整体架构已经为将来的扩展做好了准备。当需要增加新的 Bot "身份" 时，主要工作将是：

* 在 `.env` 中添加新的 Token。
* 可能需要在 `config/app_config.yml` 和 `config/prompts.yml` 中为新的 "身份" 添加特定配置或 Prompt 关联。
* `InstanceManager` 会自动加载并运行新的 Bot 实例。
* 业务逻辑层 (`message_processing`) 需要能够根据传入的 Bot "身份" ID 来调整行为 (如果需要差异化)。

这个蓝图强调了业务逻辑的通用性和与 Telegram Bot 实例的解耦，使得未来增加更多“马甲”Bot 变得更加容易，而不需要重写核心的对话和群聊管理功能。