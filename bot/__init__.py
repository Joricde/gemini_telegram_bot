import json
import os

import yaml
from dotenv import load_dotenv
from google.generativeai.types.safety_types import HarmCategory, HarmBlockThreshold

load_dotenv()

# 从环境变量读取配置文件路径
config_path = os.environ.get("CONFIG_PATH", "config/config.yml")
prompts_path = os.environ.get("PROMPTS_PATH", "config/prompts.json")

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open(prompts_path, "r", encoding="utf-8") as f:
    prompts = json.load(f)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")  # 改为小写
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # 改为小写

AVAILABLE_MODELS = config.get("models", {})
PROMPTS = prompts
DEFAULT_PROMPT_NAME = "lilith_concise"
DEFAULT_PROMPT = prompts.get(DEFAULT_PROMPT_NAME, {})
SYSTEM_INSTRUCTION = DEFAULT_PROMPT.get("system_instruction", "")
GENERATION_CONFIG = {
    "temperature": DEFAULT_PROMPT.get("temperature", 0.9),
    "top_p": DEFAULT_PROMPT.get("top_p", 1.0),
    "top_k": DEFAULT_PROMPT.get("top_k", 60),
    "max_output_tokens": DEFAULT_PROMPT.get("max_output_tokens", 2048),
}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
}

if GOOGLE_API_KEY is None:  # 使用小写变量名
    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

if BOT_TOKEN is None:  # 使用小写变量名
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")

__version__ = "0.1.0"