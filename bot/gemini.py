import os

import google.generativeai as genai
import yaml

# 加载配置文件
with open("config/config.yml", "r") as f:
    config = yaml.safe_load(f)

with open("config/prompts.yml", "r") as f:
    prompts = yaml.safe_load(f)

# 获取默认的 system instruction 和生成参数
default_prompt = prompts["default"]
system_instruction = default_prompt["system_instruction"]
generation_config = {
    "temperature": default_prompt["temperature"],
    "top_p": default_prompt["top_p"],
    "top_k": default_prompt["top_k"],
    "max_output_tokens": default_prompt["max_output_tokens"],
    "response_mime_type": default_prompt["response_mime_type"],
}

# ...
# 配置 Gemini API 客户端
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config.get(
    "credentials_path", "path/to/your/credentials.json"
)
genai.configure()

# Gemini 模型和生成配置
available_models = config.get("models", {})

# 用户模型
user_models = {}

def get_available_models():
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