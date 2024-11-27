# gemini on telegram bot
### 需求简介
为了构建telegrambot 我首选应该准备一下sdk
```txt
google-generativeai
python-telegram-bot

```
并且准备好配置文件
我需要实现以下功能
1. 首先bot应该能获取到用户信息用来判断用户来源和记录
2. 对于用户给bot发送的信息,应该能做出响应
3. 允许用户切换bot模型以及设定
4. 对话记录

### 结构
项目目录结构构建如下
```text
gemini-telegram-bot/
├── bot/
│   ├── __init__.py
│   ├── handlers.py
│   ├── gemini.py
│   ├── database.py
│   ├── utils.py
├── config/
│   ├── gemini.yml
│   ├── prompts.yml
│   ├── 
├── main.py
├── requirements.txt
```
### 现在开始,为项目目录的文件进行逐个解释
##### 总体运行逻辑
通过main 来允许整个项目
首先我应该构建一个```main.py```作为入口调用其他板块

##### main.py
该文件作为程序的入口，负责初始化Telegram Bot和注册处理器。
##### bot/
该目录包含bot的核心功能模块。

###### \_\_init\_\_.py
该文件用于将bot目录定义为一个Python包。

###### handlers.py
该文件包含bot的消息处理器，负责处理不同类型的消息，例如文本消息、命令消息等。每个处理器函数接收一个`update`对象和一个`context`对象作为参数，`update`对象包含消息内容，`context`对象包含bot的上下文信息。

###### gemini.py
该文件包含与Gemini API交互的代码，例如发送请求、接收响应等。

###### database.py
该文件包含与数据库交互的代码，例如存储用户信息、对话记录等。

###### utils.py
该文件包含一些工具类函数，例如日志记录、错误处理等。

##### config/
该目录包含bot的配置文件。

###### gemini.yml
该文件包含Gemini API的配置信息，例如API密钥、模型ID等。

###### prompts.yml
该文件包含对Gemini的system_instruction以及模型的temperature top_P等设定。

