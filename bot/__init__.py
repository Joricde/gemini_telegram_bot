import json
import os

import yaml
from dotenv import load_dotenv
from google.generativeai.types.safety_types import HarmCategory, HarmBlockThreshold

load_dotenv()

print(os.getcwd())

with open("config/config.yml", "r",  encoding="utf-8") as f:
    config = yaml.safe_load(f)

with open("config/prompts.json", "r", encoding="utf-8") as f:
    prompts = json.load(f)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

AVAILABLE_MODELS  = config.get("models", {})
PROMPTS = prompts
DEFAULT_PROMPT = prompts["lilith_concise"]
SYSTEM_INSTRUCTION  = DEFAULT_PROMPT["system_instruction"]
GENERATION_CONFIG  = {
    "temperature": DEFAULT_PROMPT["temperature"],
    "top_p": DEFAULT_PROMPT["top_p"],
    "top_k": DEFAULT_PROMPT["top_k"],
    "max_output_tokens": DEFAULT_PROMPT["max_output_tokens"],
}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
}

if GOOGLE_API_KEY is None:
    raise ValueError("GOOGLE_API_KEY environment variable is not set.")

if BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set.")
