import os

from google.ai.generativelanguage_v1beta import HarmCategory
from google.generativeai.types import HarmBlockThreshold

import bot
from utils import logger
import google.generativeai as genai
import yaml


class Gemini:
    def __init__(self, model_name="gemini-1.5-flash"):
        assert model_name in bot.AVAILABLE_MODELS , f"Unknown model: {model_name}"
        self.model_name = model_name
        self.model  = genai.GenerativeModel(
            model_name=model_name,
            generation_config=bot.GENERATION_CONFIG,
            system_instruction=bot.SYSTEM_INSTRUCTION,
            safety_settings=bot.SAFETY_SETTINGS
        )
    genai.configure(api_key=bot.GOOGLE_API_KEY)
    model = genai.GenerativeModel()

    @staticmethod
    def get_available_models():
        """
        获取可用的模型列表。
        """
        return list(bot.AVAILABLE_MODELS.keys())

    def set_current_model(self, user_id, model_id):
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
        # TODO: 从 prompts.json 中读取 system_instruction
        system_instruction = ""

        generation_config = available_models[model_id]
        response = genai.generate_text(
            model=model_id,
            prompt=prompt,
            generation_config=generation_config,
            system_instruction=system_instruction,
        )
        return response.text