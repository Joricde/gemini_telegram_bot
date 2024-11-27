import os

from google.ai.generativelanguage_v1beta import HarmCategory
from google.generativeai.types import HarmBlockThreshold

from bot import GOOGLE_API_KEY
from utils import logger
import google.generativeai as genai
import yaml

# 加载配置文件
with open("config/config.yml", "r") as f:
    config = yaml.safe_load(f)

with open("config/prompts.yml", "r") as f:
    prompts = yaml.safe_load(f)

available_models = config.get("models", {})
default_prompt = prompts["default"]
system_instruction = default_prompt["system_instruction"]
generation_config = {
    "temperature": default_prompt["temperature"],
    "top_p": default_prompt["top_p"],
    "top_k": default_prompt["top_k"],
    "max_output_tokens": default_prompt["max_output_tokens"],
    "response_mime_type": default_prompt["response_mime_type"],
}
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.OFF,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.OFF,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.OFF,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.OFF,
}

class Gemini:
    def __init__(self, model="gemini-1.5-flash"):
        assert model in available_models, f"Unknown model: {model}"
        self.model = model
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel()

    def get_available_models(self):
        """
        获取可用的模型列表。
        """
        return list(available_models.keys())

    def set_current_model(user_id, model_id):
        """
        设置用户当前使用的模型。
        """
        user_models[user_id] = model_id

    def get_current_model(user_id):
        """
        获取用户当前使用的模型。
        """
        return user_models.get(user_id, "gemini-1.5-flash")  # 默认使用 gemini-1.5-flash

    def generate_text(model_id, prompt, user_id):
        """
        使用指定的模型生成文本。
        """
        # system_instruction = prompts.get(user_id, {}).get("system_instruction", "")
        # TODO: 从 prompts.yml 中读取 system_instruction
        system_instruction = ""

        generation_config = available_models[model_id]
        response = genai.generate_text(
            model=model_id,
            prompt=prompt,
            generation_config=generation_config,
            system_instruction=system_instruction,
        )
        return response.text