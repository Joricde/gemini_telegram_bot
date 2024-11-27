# Gemini Telegram Bot

这是一个使用 Gemini 模型构建的 Telegram Bot，可以与用户进行对话、回答问题、生成文本等。

## 功能

*   使用 Gemini 模型进行自然语言处理。
*   支持多种 Gemini 模型，用户可以根据需要切换模型。
*   可以自定义模型的生成参数，例如 temperature、top_p 等。
*   记录用户对话历史。
*   ...

## 使用方法

1.  安装依赖库：
    ```bash
    pip install -r requirements.txt
    ```

2.  配置 `config.yml` 文件：
    *   设置 `gemini.credentials_path` 为你的 Gemini API 凭据文件路径。
    *   根据需要修改 `gemini.models` 中的模型配置参数。
    *   设置 `database.path` 为数据库文件路径。

3.  设置环境变量 `TELEGRAM_BOT_TOKEN` 为你的 Telegram Bot Token。

4.  运行 `main.py` 启动 Bot：
    ```bash
    python main.py
    ```

## 命令

*   `/start`：显示欢迎消息和帮助信息。
*   `/set_model <model_id>`：设置用户当前使用的模型。
*   `/get_models`：获取可用的模型列表。

## 开发

### 项目结构