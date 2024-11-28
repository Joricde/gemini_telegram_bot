from main_simple import get_model

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
│   ├── gemini.py
│   ├── database.py
│   ├── handlers.py
│   ├── run.py
│   ├── utils.py
├── config/
│   ├── gemini.yml
│   ├── prompts.yml
├── main.py
├── requirements.txt
```
### 现在开始,为项目目录的文件进行逐个解释
##### 总体运行逻辑
通过main 来允许整个项目
首先我应该构建一个```main.py```作为入口调用其他板块(

##### main.py
该文件作为程序的入口，负责初始化项目----对于本项目仅仅需要调用run.py即可
##### bot/
该目录包含bot的核心功能模块。
###### \_\_init\_\_.py
该文件用于将bot目录定义为一个Python包。
这里读取初始化时候config以及prompts中的默认值
参考代码如下

```python
import os

import yaml
from dotenv import load_dotenv
from google.ai.generativelanguage_v1beta import HarmCategory
from google.generativeai.types import HarmBlockThreshold

load_dotenv()

print(os.getcwd())

with open("config/config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open("config/prompts.json", "r", encoding="utf-8") as f:
    prompts = yaml.safe_load(f)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

AVAILABLE_MODELS = config.get("models", {})
DEFAULT_PROMPT = prompts["default"]
SYSTEM_INSTRUCTION = DEFAULT_PROMPT["system_instruction"]
GENERATION_CONFIG = {
    "temperature": DEFAULT_PROMPT["temperature"],
    "top_p": DEFAULT_PROMPT["top_p"],
    "top_k": DEFAULT_PROMPT["top_k"],
    "max_output_tokens": DEFAULT_PROMPT["max_output_tokens"],
}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.OFF,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.OFF,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.OFF,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.OFF,
}

if GOOGLE_API_KEY is None:
    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

if BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")

```

###### handlers.py
该文件包含bot的消息处理器，负责处理不同类型的消息，例如文本消息、命令消息等。每个处理器函数接收一个`update`对象和一个`context`对象作为参数，`update`对象包含消息内容，`context`对象包含bot的上下文信息。

###### gemini.py
首先,我应该创建一个Gemini类,用于为多用户个能够自行选择属于自己的 prompt 中的配置,
这个Gemini类应该是对    ```genai.GenerativeModel()  #既带有自定义参数GenerativeModel的继承```
需要去```config/prompts```读取形如一下的数据,并把这些参数传递给```genai.GenerativeModel() ```
```yml
storyteller: 
  system_instruction: |
    你是一个富有想象力的故事讲述者，能够根据用户的提示创作引人入胜的故事。
  temperature: 0.8
  top_p: 0.9
  top_k: 50
  max_output_tokens: 2048
```
建立类中的方法,Gemini类根据init.py中的变量,设置自己的类变量(需要考虑调用来设置为公开变量或者私有变量)并设置一下方法,参考如下
我应该不全这些方法,并给出参数的类型以及返回的类型
```python
def get_current_model(self):
    pass
def set_current_model(self, model_name):
    # TODO: 我应该根据init.py中的给出的变量设置
    pass
def set_current_prompt(self,prompt):
    # TODO:我应该为根据本init中给出的DEFAULT_PROMPT来为genai.GenerativeModel设置参数
    pass

def generate_text(self):
    # TODO: 采用GenerativeModel.start_chat()来为用户回复(以便可以带记忆的和用户对话)
    pass

```


###### database.py
该文件包含与数据库交互的代码，例如存储用户信息、对话记录等。
首先,应该有一张用户表,表示可使用gemini的权限,应该记录用户的id 以及
username(从telegram.ext处获取---update里包含了用户信息),并且应该记录用户当前使用的模型.
然后应该创建另一张表格,来记录用户开启的每个对话()

###### utils.py
该文件包含一些工具类函数，例如日志记录、错误处理等。

##### config/
该目录包含bot的配置文件。

###### gemini.yml
该文件包含Gemini API的配置信息，例如API密钥、模型ID等。

###### prompts.yml
该文件包含对Gemini的system_instruction以及模型的temperature top_P等设定。

