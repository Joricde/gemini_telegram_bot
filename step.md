# Gemini Telegram Bot 开发路线图 (v2)

## 项目现状评估

通过对现有代码库的全面分析，项目已经实现了强大且稳定的核心功能，远超出了早期规划的范畴。目前的完成度总结如下：

* **阶段一：基础架构与核心服务 - 已完成**
    * **环境配置**: 已通过 `.env`, `app_config.yml`, `prompts.yml` 实现完全配置化。
    * **日志系统**: 已通过 `bot/utils.py` 建立。
    * **数据库模块**: 已通过 SQLAlchemy 定义了完整的 `models.py` 和 `crud.py`，支持用户、角色、群组设置、会话状态和消息缓存。
    * **Gemini 服务**: `bot/gemini_service.py` 已封装完毕，并支持为群聊构建复合型 System Instruction。

* **阶段二：高级私聊功能与会话管理 - 已完成**
    * **私聊逻辑**: `bot/message_processing/private_chat.py` 中已实现完整的私聊处理。
    * **高级会话管理**: 成功实现了基于 `is_active` 标志的会话管理机制。
        * **会话超时**: 超过1小时不活动，自动开启新会话。
        * **角色切换**: 切换角色 (`/my_prompts` 中选择) 会自动开启新会话，保证对话上下文的纯粹性。
    * **高级角色(Prompt)管理**:
        * 通过 `/my_prompts` 命令和回调，实现了对私人角色的完整可视化管理（增、删、改、查、选）。
        * 通过 `/upload_prompt` 命令和 `ConversationHandler`，实现了引导式创建新角色的流程。
        * 通过回调按钮和 `ConversationHandler`，实现了引导式编辑角色指令的流程。

* **阶段三 & 四：群聊功能 - 待实现**
    * 数据库和 CRUD 函数已准备就绪，但 Telegram 的群聊消息处理器尚未在 `main.py` 中注册和实现。

---

## 下一步开发计划

### 阶段三：群聊核心功能实现

此阶段的目标是让机器人在群组中能够响应互动，并支持不同的会话模式。

1.  **创建群聊逻辑模块**:
    * 新建文件 `bot/message_processing/group_chat.py`。
    * 该文件将包含处理所有群聊消息的核心逻辑函数。

2.  **实现群聊消息处理器**:
    * 在 `main.py` 中，添加一个新的 `MessageHandler`，用于监听群聊消息 ( `filters.ChatType.GROUPS` )。
    * 此处理器应将 `update` 和 `context` 传递给 `group_chat.py` 中的主处理函数。

3.  **实现直接互动逻辑 (在 `group_chat.py` 中)**:
    * 编写函数 `handle_group_message`。
    * 函数首先检查消息是否是对机器人的直接互动（如 `@Bot` 或回复 Bot 的消息）。
    * 从数据库获取或创建该群组的 `GroupSetting`。
    * 根据 `GroupSetting` 中的 `current_mode` 决定下一步操作。

4.  **实现独立会话模式 (`individual` mode)**:
    * 如果模式为 `individual`，则会话逻辑与私聊类似，但 `ChatSessionState` 的主键将由 `(telegram_chat_id, telegram_user_id)` 共同决定。
    * 为在该群组中与机器人互动的每个用户维护独立的对话历史。
    * 同样应用会话超时逻辑。

5.  **实现共享会话模式 (`shared` mode)**:
    * 如果模式为 `shared`，所有直接互动都将使用同一个 `ChatSessionState`，该会话仅由 `telegram_chat_id` 决定 (`telegram_user_id` 为 `None`)。
    * 整个群组共享一个对话历史。

6.  **实现模式切换命令**:
    * 在 `group_chat.py` 中添加 `set_group_mode_command` 函数。
    * 该函数仅限群管理员使用。
    * 实现 `/mode <shared|individual>` 命令，用于更新数据库中对应群组的 `GroupSetting`。
    * 在 `main.py` 中注册此 `CommandHandler`。

---

### 阶段四：高级群聊功能 - 动态随机插嘴

此阶段的目标是让机器人在共享模式下能更智能、更自然地参与群聊，解决用户提出的“动态触发频率”需求。

1.  **建立内存缓存**:
    * 在 `group_chat.py` 中，创建一个全局字典 `GROUP_REPLY_TRIGGER_CACHE`，结构为 `{group_id: message_count}`。
    * 此缓存用于实时追踪每个群组在机器人未回复期间的消息数量，无需频繁读写数据库。

2.  **监听并计数所有群消息**:
    * 修改 `handle_group_message` 函数。
    * 对于**任何**收到的群消息（无论是否 `@Bot`），都执行以下操作：
        * 将消息存入数据库的 `GroupMessageCache` 表中（调用 `crud.add_message_to_cache`），用于提供插话时的上下文。
        * 如果群模式为 `shared` 且 `random_reply_enabled` 为 `True`，则将该 `group_id` 在 `GROUP_REPLY_TRIGGER_CACHE` 中的计数器加一。

3.  **实现动态概率触发算法**:
    * 在消息计数后，立即进行插嘴触发判断。
    * 从 `app_config.yml` 的 `random_reply_parameters` 读取 `listen_message_count` (N) 和 `base_probability_p_denominator` (P)。
    * **触发概率** `Prob = min(1.0, (current_message_count / N) * (1 / P))`。
        * 这个公式意味着，当消息数达到 `listen_message_count` 时，触发概率会显著提高，同时受基础概率 `P` 的调节。
    * 生成一个随机数，如果小于 `Prob`，则触发插嘴。

4.  **实现插嘴逻辑**:
    * 如果触发插嘴：
        * 从数据库 (`GroupMessageCache`) 中获取最近的 N 条消息作为上下文。
        * 将这些消息格式化成一个连贯的对话历史字符串。
        * 使用群组的共享角色 Prompt 和格式化后的上下文，调用 `GeminiService` 生成回复。
        * 将回复发送到群组。
        * **重置** `GROUP_REPLY_TRIGGER_CACHE` 中该 `group_id` 的计数器为 `0`。

---

### 阶段五：功能优化与统一命令

此阶段的目标是根据用户反馈优化体验，并统一常用命令。

1.  **创建统一的 `/new` 命令**:
    * 在 `bot/telegram_adapter/commands.py` 中创建一个新的命令处理器 `new_command_handler`。
    * 在 `main.py` 中注册该 `CommandHandler`。

2.  **实现 `/new` 命令逻辑**:
    * 处理器通过 `update.message.chat.type` 判断当前是私聊还是群聊。
    * **私聊**:
        * 直接为该 `user_id` 调用 `crud.create_new_chat_session`。
        * 该函数会自动归档旧会话，并使用用户当前激活的 Prompt（或默认 Prompt）开启一个全新的会话。
    * **群聊**:
        * 首先获取群组的 `GroupSetting` 来判断模式。
        * **`individual` 模式**: 为当前 `user_id` 和 `group_id` 调用 `create_new_chat_session`，重置该用户在群内的个人对话。
        * **`shared` 模式**: 为 `group_id` (其中 `user_id` 为 `None`) 调用 `create_new_chat_session`，重置整个群组的共享对话。
    * 向用户发送明确的确认消息，例如 “新的对话已经开始。” 或 “群聊历史已重置。”。

---

### 阶段六：文档更新与最终测试

1.  **全面测试**:
    * 测试所有私聊和群聊功能，特别是模式切换、随机插嘴的概率和 `/new` 命令在不同场景下的表现。
2.  **更新文档**:
    * 更新 `README.md`，详细说明所有新功能、命令及其用法。
3.  **代码审查与优化**:
    * 清理代码，添加必要的注释，确保项目结构清晰、易于维护。