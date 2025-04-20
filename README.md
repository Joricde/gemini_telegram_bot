# Gemini Telegram Bot

这是一个使用 Gemini 模型构建的 Telegram Bot，可以与用户进行对话、回答问题、生成文本等。

## 功能

*  使用 Gemini 模型进行自然语言处理。
*  支持多种模型和预设。
*  重置对话功能。

## 使用方法

1. 安装依赖库：
   ```bash
   pip install -r requirements.txt
   ```
2. 配置 conf.yml 文件：
   - 设置 GEMINI_API_KEY 为你的 Gemini API 密钥。
   - 设置 TELEGRAM_BOT_TOKEN 为你的 Telegram Bot Token。
   - 运行 main.py 启动 Bot：
## 命令
- /models：选择模型和预设。
- /new：重置当前对话。