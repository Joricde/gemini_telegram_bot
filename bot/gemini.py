from __init__ import (
    AVAILABLE_MODELS,
    DEFAULT_PROMPT_NAME,
    GENERATION_CONFIG,
    GOOGLE_API_KEY,
    PROMPTS,
    SAFETY_SETTINGS,
    SYSTEM_INSTRUCTION,
)

import google.generativeai as genai

# 配置 API 密钥
genai.configure(api_key=GOOGLE_API_KEY)


class Gemini:
    def __init__(self,
                 model=AVAILABLE_MODELS[0],
                 prompt=DEFAULT_PROMPT_NAME,
                 system_instruction=SYSTEM_INSTRUCTION,
                 generation_config=GENERATION_CONFIG,
                 safety_settings=SAFETY_SETTINGS, ):
        self._model_name = model
        self._prompt = prompt
        self._system_instruction = system_instruction
        self._generation_config = generation_config
        self._safety_settings = safety_settings
        self._model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=self._system_instruction,
            generation_config=self._generation_config,
            safety_settings=self._safety_settings,
        )
        self.user_data = {}

    def generate_text_response(self, chat_id, message):
        chat_session = self.user_data.setdefault(
            chat_id,
            {
                "chat_session": self._model.start_chat(),
                "model": self._model_name,
                "prompt": self._prompt,
            },
        )["chat_session"]

        response = chat_session.send_message(message)
        return response

    def generate_media_response(self, chat_id, media_type, media_content, message=""):
        chat_session = self.user_data.setdefault(
            chat_id,
            {
                "chat_session": self._model.start_chat(),
                "model": self._model_name,
                "prompt": self._prompt,
            },
        )["chat_session"]

        # 处理多模态输入
        if media_type == "image":
            if message:
                # 文字 + 图片
                response = chat_session.send_message([message, media_content])
            else:
                # 仅图片
                response = chat_session.send_message(media_content)
            return response
        elif media_type == "audio":
            if message:
                # 文字 + 音频
                response = chat_session.send_message([message, media_content])
            else:
                # 仅音频
                response = chat_session.send_message(media_content)
            return response
        else:
            raise ValueError(f"Unsupported media type: {media_type}")

    def change_model(self, chat_id, model):
        # 更新用户的模型和 ChatSession
        self.user_data.setdefault(
            chat_id,
            {
                "chat_session": self._model.start_chat(),
                "model": self._model_name,
                "prompt": self._prompt,
            },
        )["model"] = model

        # 使用实例变量创建 GenerativeModel 实例
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction=self._system_instruction,
            generation_config=self._generation_config,
            safety_settings=self._safety_settings,
        )
        self.user_data[chat_id]["chat_session"] = self._model.start_chat()
        return "模型已更改为 " + model

    def change_prompt(self, chat_id, prompt):
        self.user_data.setdefault(
            chat_id,
            {
                "chat_session": self._model.start_chat(),
                "model": self._model_name,
                "prompt": self._prompt,
            },
        )["prompt"] = prompt
        return "预设已更改为 " + prompt

    def reset(self, chat_id):
        # 重置用户的 ChatSession
        self.user_data[chat_id]["chat_session"] = self._model.start_chat()
        return "对话已重置"

    def remove_last_message(self, chat_id):
        # 删除用户最后一条消息和助手最后一条回复
        if chat_id in self.user_data and len(self.user_data[chat_id]["chat_session"].history) >= 2:
            self.user_data[chat_id]["chat_session"].rewind()
            return "已删除最后一条消息"
        else:
            return "没有消息可删除"

    def edit_last_message(self, chat_id, new_message):
        # 编辑用户最后一条消息，并重新生成回复
        if chat_id in self.user_data and len(self.user_data[chat_id]["chat_session"].history) >= 1:
            # 使用 ChatSession 的 rewind 方法删除最后一条消息
            self.user_data[chat_id]["chat_session"].rewind()

            # 使用 ChatSession 的 send_message 方法发送新的消息
            response = self.user_data[chat_id]["chat_session"].send_message(new_message)
            return response.text
        else:
            return "没有消息可编辑"
