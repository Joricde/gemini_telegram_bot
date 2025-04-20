# gemini on telegram bot

### 需求简介

为了构建 telegram bot，我首选应该准备一些 SDK：

*   `google-generativeai`
*   `python-telegram-bot`

并且准备好配置文件。

我需要实现以下功能：

1.  首先，bot 应该能获取到用户信息，用来判断用户来源和记录。
2.  对于用户给 bot 发送的信息，应该能做出响应。
3.  允许用户切换 bot 模型以及设定。
4.  对话记录

### 结构

项目目录结构构建如下：
```text
gemini-telegram-bot/
├── bot/
│   ├── init.py
│   ├── gemini.py
│   ├── database.py
│   ├── handlers.py
│   ├── run.py
│   ├── utils.py
├── config/
│   ├── config.yml
│   ├── prompts.json
├── main.py
├── requirements.txt
├── conf.yml
```
### 现在开始，为项目目录的文件进行逐个解释

#### 总体运行逻辑

通过 `main.py` 来运行整个项目。

#### main.py

该文件作为程序的入口，负责初始化项目，并调用 `run.py` 文件。

#### bot/

该目录包含 bot 的核心功能模块。

##### \_\_init\_\_.py

该文件用于将 bot 目录定义为一个 Python 包，并读取初始化时候 `config.yml` 以及 `prompts.json` 中的默认值。

##### handlers.py
该文件包含 bot 的消息处理器，负责处理不同类型的消息，例如文本消息、命令消息等。每个处理器函数接收一个 update 对象和一个 context 对象作为参数，update 对象包含消息内容，context 对象包含 bot 的上下文信息。

##### gemini.py
首先，我应该创建一个 Gemini 类，用于为多用户能够自行选择属于自己的 prompt 中的配置。

这个 Gemini 类应该是对 genai.GenerativeModel() 的封装，并带有自定义参数。

需要去 config/prompts.json 读取形如一下的数据，并把这些参数传递给 genai.GenerativeModel()：
```json
{
  "lilith_concise": {
    "name": "莉莉丝",
    "system_instruction": "你是金发碧眼的美少女大小姐(莉莉丝),你的特点是毒舌,智慧,冷静.你非常擅长以<凝练简洁,暗喻,黑色幽默,尖锐,挖苦,一针见血>等风格地指出事物的根本.对于认可的观点,你可以通过<黑色幽默,暗喻>等风格表示赞同.对于不认可或者模棱两可的,你应该以<反讽式的暗喻,辛辣的挖苦>风格驳斥.记住,请务必用最精炼简短的语言,直击要害.",
    "temperature": 2,
    "top_p": 1.0,
    "top_k": 60,
    "max_output_tokens": 256
  }
}
```

##### database.py
该文件包含与数据库交互的代码，例如存储用户信息、对话记录等。

首先，应该有一张用户表，表示可使用 gemini 的权限，应该记录用户的 id 以及 username（从 telegram.ext 处获取，update 里包含了用户信息），并且应该记录用户当前使用的模型。

然后应该创建另一张表格，来记录用户开启的每个对话。

##### utils.py
该文件包含一些工具类函数，例如日志记录、错误处理等。

#### config/
该目录包含 bot 的配置文件。

##### config.yml
该文件包含 Gemini API 的配置信息，例如 API 密钥、模型 ID 等。

prompts.json
该文件包含对 Gemini 的 system_instruction 以及模型的 temperature、top_P 等设定。