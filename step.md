# 项目架构与实施计划

## 步骤 1: 基础 (核心与数据库)
* **项目结构 (Project Structure):** 创建上述列出的目录和空的 `__init__.py` 文件。
* **配置 (Configuration - bot/core/config.py):** 创建一个模块，用于从 `.env` 和 `config/*.yml` 文件加载设置到易于访问的、带类型（typed variables）的变量中（例如，使用 Pydantic 或简单的 dataclasses）。所有其他模块都将从这里导入配置，而不是自行读取文件。
* **日志 (Logging - bot/core/logging.py):** 按照原始 `utils.py` 中的方式设置日志记录器 (logger)。
* **数据库模型 (Database Models - bot/database/models.py):** 定义 SQLAlchemy 表模型。我们可以使用与原始项目相同的模型（User, Prompt, ChatSessionState 等），因为它们设计良好。
* **数据库引擎 (Database Engine - bot/database/__init__.py):** 设置 SQLAlchemy 引擎 (engine) 和 `SessionLocal`。
* **CRUD 函数 (CRUD Functions - bot/database/crud.py):** 实现与数据库表交互的函数。这是数据操作到 Python 函数的直接转换。
* **目标 (Goal):** 在此步骤结束时，我们将拥有一个已配置的应用程序外壳 (application shell) 和一个功能齐全的数据层 (data layer)，可以独立进行测试。

---

## 步骤 2: 大脑 (服务)
* **Gemini 服务 (Gemini Service - bot/services/gemini_service.py):** 此服务将专门负责与 Google Gemini API 通信。它将接收提示 (prompt)、历史记录 (history) 和生成参数 (generation parameters)，并返回响应 (response)。它对 Telegram 或我们的数据库结构一无所知。
* **提示服务 (Prompt Service - bot/services/prompt_service.py):** 此服务将处理创建、检索、更新和删除提示的逻辑。它将使用 `bot.database.crud` 来执行这些操作。
* **聊天服务 (Chat Service - bot/services/chat_service.py):** 这是业务逻辑中最关键的部分。它将包含诸如 `handle_private_message(...)` 之类的函数。此函数将：
    * 使用 `crud.get_or_create_user`。
    * 实现会话管理逻辑 (session management logic)（检查活动会话 (active sessions)、处理超时 (timeouts)、创建新会话）。
    * 使用 `gemini_service.send_message` 获取 AI 响应。
    * 使用 `crud.update_chat_history` 保存对话。
    * 返回最终的文本响应，以便发送给用户。
* **目标 (Goal):** 在此步骤结束时，我们将拥有一个功能齐全的“无头” (headless) 机器人。我们可以编写一个测试脚本来调用 `chat_service.handle_private_message` 并验证其是否正常工作，所有这些都无需任何 Telegram 代码。

---

## 步骤 3: 接口 (Telegram)
* **键盘 (Keyboards - bot/telegram/keyboards.py):** 创建生成 `InlineKeyboardMarkup` 对象（例如 `/my_prompts` 的键盘）的函数。这将使处理程序文件 (handler files) 更整洁。
* **处理程序 (Handlers - bot/telegram/handlers/*.py):** 这些是“胶水”代码 (glue code)。它们应该非常薄 (thin)。
    * `/my_prompts` 的命令处理程序（例如在 `commands.py` 中）将简单地调用 `keyboards.py` 中的键盘生成函数并发送消息。
    * 消息处理程序（在 `messages.py` 中）将从 `Update` 对象中提取 `user_id` 和文本，并将它们传递给 `chat_service.handle_private_message`。然后，它接收返回的字符串并回复用户。
    * 回调处理程序 (callback handler)（在 `callbacks.py` 中）将解析 `callback_data`，调用适当的服务函数（例如 `prompt_service.set_active_prompt`），然后编辑消息。
* **应用程序设置 (Application Setup - bot/telegram/app.py):** 此模块将导入所有处理程序，初始化 `telegram.ext.Application`，并注册它们。这使得 `main.py` 保持简洁。
* **目标 (Goal):** 在此步骤结束时，“大脑”已连接到 Telegram 接口。机器人应该对用户完全可用。

---

## 步骤 4: 执行与完善
* **主入口点 (Main Entry Point - main.py):** 此文件将非常简短。它主要做两件事：`from bot.telegram.app import run` 然后 `run()`。
* **README 与测试 (README & Testing):** 编写 `README.md` 以反映新的、清晰的架构，并在 `tests/` 目录中添加单元测试 (unit tests) 或集成测试 (integration tests) 以确保可靠性。