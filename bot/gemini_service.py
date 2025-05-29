import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold, ContentDict
from typing import List, Dict, Any, Optional, Tuple

from bot import GEMINI_API_KEY, APP_CONFIG, PROMPTS_CONFIG, GROUP_CHAT_SETTINGS  # Import GROUP_CHAT_SETTINGS
from bot.utils import log
from bot.database.models import Prompt as PromptModel  # To avoid confusion

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    log.critical("GEMINI_API_KEY not found. GeminiService will not function.")


def _deserialize_history(json_history: Optional[List[Dict[str, Any]]]) -> Optional[List[ContentDict]]:
    if not json_history:
        return None
    deserialized = []
    for item in json_history:
        try:
            parts_data = item.get('parts', [])
            if not isinstance(parts_data, list):
                log.warning(f"Skipping history item due to invalid parts format: {item}")
                continue
            reconstructed_parts = []
            for part_item in parts_data:
                if isinstance(part_item, dict) and 'text' in part_item:
                    reconstructed_parts.append({'text': part_item['text']})
                else:
                    log.warning(f"Skipping part due to unknown format: {part_item} in history item: {item}")
            if not reconstructed_parts:
                log.warning(f"No valid parts found for history item after reconstruction: {item}")
                continue
            content_item = ContentDict(role=item.get('role', 'user'), parts=reconstructed_parts)
            deserialized.append(content_item)
        except Exception as e:
            log.error(f"Error deserializing history item '{item}': {e}", exc_info=True)
            continue
    return deserialized if deserialized else None


class GeminiService:
    def __init__(self):
        self.gemini_global_settings = APP_CONFIG.get("gemini_settings", {})
        self.default_gen_params_config = self.gemini_global_settings.get("default_generation_parameters", {})
        self.default_base_model = self.gemini_global_settings.get("default_base_model",
                                                                  "gemini-1.5-flash-latest")  # Updated default

        self.default_safety_settings = {
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        }

        # Load group chat header template
        self.group_headers_template = GROUP_CHAT_SETTINGS.get("default_system_headers_template", "")
        if not self.group_headers_template:
            log.warning(
                "default_system_headers_template not found in GROUP_CHAT_SETTINGS. Group chat composite prompts may not work.")

        log.info("GeminiService initialized.")
        if not GEMINI_API_KEY:
            log.warning("GeminiService initialized without API KEY. Calls will fail.")

    def _get_model_and_generation_config(
            self,
            prompt_config: Optional[PromptModel] = None,
            session_base_model: Optional[str] = None
    ) -> Tuple[str, GenerationConfig]:
        """
        Determines the effective model name and generation config.
        System instruction is handled separately.
        """
        model_name = self.default_base_model
        if prompt_config and prompt_config.base_model_override:
            model_name = prompt_config.base_model_override
        if session_base_model and session_base_model in self.gemini_global_settings.get("available_base_models", []):
            model_name = session_base_model

        gen_params = self.default_gen_params_config.copy()
        if prompt_config:
            if prompt_config.temperature is not None: gen_params["temperature"] = prompt_config.temperature
            if prompt_config.top_p is not None: gen_params["top_p"] = prompt_config.top_p
            if prompt_config.top_k is not None: gen_params["top_k"] = prompt_config.top_k
            if prompt_config.max_output_tokens is not None: gen_params[
                "max_output_tokens"] = prompt_config.max_output_tokens

        generation_config_obj = GenerationConfig(**gen_params)
        return model_name, generation_config_obj

    def start_chat_session(
            self,
            prompt_config: PromptModel,  # The primary prompt object
            session_base_model: Optional[str] = None,
            serialized_history: Optional[List[Dict[str, Any]]] = None,
            group_role_payload_instruction: Optional[str] = None  # For group shared mode
    ) -> Optional[genai.ChatSession]:
        if not GEMINI_API_KEY:
            log.error("Cannot start chat session: GEMINI_API_KEY is not configured.")
            return None
        if not prompt_config:  # Should always be provided, even if it's a generic one for group chats
            log.error("Cannot start chat session: prompt_config is required.")
            return None

        model_name, generation_config = self._get_model_and_generation_config(
            prompt_config=prompt_config,
            session_base_model=session_base_model
        )

        final_system_instruction: Optional[str]
        if group_role_payload_instruction and self.group_headers_template:
            # This is for group shared mode, construct composite system instruction
            try:
                final_system_instruction = self.group_headers_template.replace(
                    "{USER_CUSTOM_ROLE_PROMPT}",
                    group_role_payload_instruction
                )
                log.debug(f"Using composite system instruction for group chat. Role: '{prompt_config.name}'")
            except Exception as e:
                log.error(
                    f"Error formatting group_headers_template: {e}. Falling back to prompt_config.system_instruction")
                final_system_instruction = prompt_config.system_instruction
        else:
            # Standard private chat or individual group interaction
            final_system_instruction = prompt_config.system_instruction
            log.debug(f"Using direct system instruction for prompt: '{prompt_config.name}'")

        if not final_system_instruction:  # Ensure it's not empty if it's critical, or pass None
            final_system_instruction = None  # Pass None to API if truly empty, instead of "" which API might treat differently.
            log.debug(f"System instruction for prompt '{prompt_config.name}' is empty/None.")

        try:
            model_instance = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
                system_instruction=final_system_instruction,
                safety_settings=self.default_safety_settings
            )
            history_for_session = _deserialize_history(serialized_history)
            chat_session = model_instance.start_chat(history=history_for_session or [])
            log.info(
                f"Chat session started with model: {model_name}, prompt: '{prompt_config.name}'. "
                f"Group role mode: {'Yes' if group_role_payload_instruction else 'No'}. "
                f"History items: {len(history_for_session or [])}"
            )
            return chat_session
        except Exception as e:
            log.error(
                f"Failed to initialize GenerativeModel or start chat for {model_name} with prompt '{prompt_config.name}': {e}",
                exc_info=True
            )
            return None

    async def send_message(
            self,
            chat_session: genai.ChatSession,
            message_text: str
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        if not chat_session:
            log.error("Cannot send message: chat_session is None.")
            return None, None
        if not GEMINI_API_KEY:
            log.error("Cannot send message: GEMINI_API_KEY is not configured.")
            return None, None

        try:
            response = await chat_session.send_message_async(message_text)
            bot_response_text = response.text
            serializable_history = []
            if chat_session.history:
                for content_message in chat_session.history:
                    parts_list = []
                    for part in content_message.parts:
                        parts_list.append({'text': part.text if hasattr(part, 'text') else ''})
                    serializable_history.append({'role': content_message.role, 'parts': parts_list})
            log.debug(f"Sent message, got response. History length: {len(chat_session.history)}")
            return bot_response_text, serializable_history
        except Exception as e:
            log.error(f"Error sending message or processing response: {e}", exc_info=True)
            return None, None


# Example Usage (for testing this module directly - you'll need to adapt MockPrompt)
if __name__ == '__main__':
    log.info("Testing GeminiService...")
    if not GEMINI_API_KEY:
        log.error("Cannot run tests: GEMINI_API_KEY is not set.")
        exit()

    # Ensure GROUP_CHAT_SETTINGS is properly loaded if APP_CONFIG is mocked or used directly
    if not GROUP_CHAT_SETTINGS.get("default_system_headers_template"):
        print("WARNING: default_system_headers_template not found in GROUP_CHAT_SETTINGS for test.")
        # Manually set for test if needed:
        # GROUP_CHAT_SETTINGS_TEMP = {"default_system_headers_template": "HEADERS: {USER_CUSTOM_ROLE_PROMPT}"}
        # Overwrite the service's template for this test run if it's missing from your actual config load during test
        # This is just for standalone testing of the script.


    class MockPrompt(PromptModel):  # Inherit from PromptModel to satisfy type hint
        def __init__(self, name, system_instruction, prompt_type, temp=None, model_override=None):
            super().__init__()  # Call parent __init__ if PromptModel has one that needs calling
            self.id = 1  # Mocked
            self.name = name
            self.system_instruction = system_instruction  # For private or as payload
            self.prompt_type = prompt_type  # Mocked
            self.temperature = temp
            self.top_p = None
            self.top_k = None
            self.max_output_tokens = None
            self.base_model_override = model_override
            self.is_system_default = False


    service = GeminiService()


    # If GROUP_CHAT_SETTINGS was not loaded correctly via APP_CONFIG for the test, manually set it on the instance for testing purposes
    # if not service.group_headers_template:
    #     service.group_headers_template = "TEST HEADERS:\n{USER_CUSTOM_ROLE_PROMPT}"

    async def run_gemini_tests():
        # Test 1: Private Chat Prompt
        log.info("\n--- Test 1: Private Chat Prompt ---")
        private_test_prompt = MockPrompt(
            name="Test Private Greeter",
            system_instruction="You are a friendly private greeter. Always start your response with 'Aloha Private!'",
            prompt_type="private"  # This would be PromptType.PRIVATE in real use
        )
        session_private = service.start_chat_session(prompt_config=private_test_prompt)
        if session_private:
            response_text, _ = await service.send_message(session_private, "How are you today?")
            if response_text:
                log.info(f"Bot (Private): {response_text}")
                assert "Aloha Private!" in response_text, "Private prompt system instruction not followed."
            else:
                log.error("Failed to get private response.")
        else:
            log.error("Failed to start private session.")

        # Test 2: Group Shared Mode Prompt
        log.info("\n--- Test 2: Group Shared Mode Prompt ---")
        group_role_payload = "I am a cheerful group helper! My replies start with 'Hey Group!'"
        # The prompt_config for group shared mode might just be a placeholder or carry default generation params
        # if the main instruction comes from the payload + headers.
        # Or, prompt_config.system_instruction IS the payload.
        group_test_prompt = MockPrompt(
            name="Test Group Helper Role",
            system_instruction=group_role_payload,  # This instruction is the PAYLOAD
            prompt_type="group_role_payload"
        )

        if not service.group_headers_template:
            log.error("Skipping group test: group_headers_template is empty in service. Check config.")
            return

        session_group = service.start_chat_session(
            prompt_config=group_test_prompt,  # This prompt provides the payload via its system_instruction
            group_role_payload_instruction=group_test_prompt.system_instruction  # Explicitly pass payload
        )
        if session_group:
            # Check the system instruction used by the model if possible (not directly exposed by SDK after creation)
            # We trust the internal logic has formed it correctly.
            log.info(f"Group session started. Model's system instruction should be composite (template + payload).")
            response_text_group, _ = await service.send_message(session_group, "What's up group?")
            if response_text_group:
                log.info(f"Bot (Group): {response_text_group}")
                # The assertion depends on how USER_CUSTOM_ROLE_PROMPT interacts with HEADERS.
                # If HEADERS dictate a prefix, and PAYLOAD dictates another, test for combined effect.
                # For this example, assume the payload's instruction is dominant for the start of the reply.
                assert "Hey Group!" in response_text_group, "Group role payload instruction not followed."
            else:
                log.error("Failed to get group response.")
        else:
            log.error("Failed to start group session.")

        log.info("\nGeminiService tests completed.")


    import asyncio

    asyncio.run(run_gemini_tests())