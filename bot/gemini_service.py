import google.generativeai as genai
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold, ContentDict
from typing import List, Dict, Any, Optional, Tuple

from bot import GEMINI_API_KEY, APP_CONFIG, PROMPTS_CONFIG  # Import loaded configurations
from bot.utils import log  # Import our logger
from bot.database.models import Prompt as PromptModel  # To avoid confusion with other Prompt types

# --- Configure the Gemini API client ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    log.critical("GEMINI_API_KEY not found. GeminiService will not function.")
    # Depending on how critical, you might raise an exception here
    # raise ValueError("GEMINI_API_KEY is not configured.")


# --- Helper function to deserialize history (if needed) ---
def _deserialize_history(json_history: Optional[List[Dict[str, Any]]]) -> Optional[List[ContentDict]]:
    """
    Converts a list of dictionaries (from JSON) back into a list of ContentDict
    suitable for initializing a Gemini ChatSession.
    """
    if not json_history:
        return None

    deserialized = []
    for item in json_history:
        try:
            # Ensure parts is a list of dicts with 'text' key, or other valid Part types
            parts_data = item.get('parts', [])
            if not isinstance(parts_data, list):  # Basic check, could be more robust
                log.warning(f"Skipping history item due to invalid parts format: {item}")
                continue

            # Reconstruct parts, assuming they are simple text parts for now
            # For more complex parts (e.g., images), this would need expansion
            reconstructed_parts = []
            for part_item in parts_data:
                if isinstance(part_item, dict) and 'text' in part_item:
                    reconstructed_parts.append({'text': part_item['text']})
                # Add handling for other part types if you support them (e.g., inline_data for images)
                else:
                    log.warning(f"Skipping part due to unknown format: {part_item} in history item: {item}")

            if not reconstructed_parts:  # If no valid parts were found for this message
                log.warning(f"No valid parts found for history item after reconstruction: {item}")
                continue

            content_item = ContentDict(role=item.get('role', 'user'), parts=reconstructed_parts)
            deserialized.append(content_item)
        except Exception as e:
            log.error(f"Error deserializing history item '{item}': {e}", exc_info=True)
            # Decide: skip item or raise error? For now, skip.
            continue
    return deserialized if deserialized else None


class GeminiService:
    """
    Manages interactions with the Google Gemini API, including model configuration,
    chat session management, and history handling.
    """

    def __init__(self):
        self.gemini_global_settings = APP_CONFIG.get("gemini_settings", {})
        self.default_gen_params_config = self.gemini_global_settings.get("default_generation_parameters", {})
        self.default_base_model = self.gemini_global_settings.get("default_base_model", "gemini-1.5-flash")

        # Define default safety settings (can be made configurable in app_config.yml if needed)
        # Setting to BLOCK_NONE for all categories as per your __init__.py in the original structure.
        # Be very careful with these settings in a production environment.
        self.default_safety_settings = {
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        }
        log.info("GeminiService initialized.")
        if not GEMINI_API_KEY:
            log.warning("GeminiService initialized without API KEY. Calls will fail.")

    def _get_effective_config(self,
                              prompt_config: Optional[PromptModel] = None,
                              session_base_model: Optional[str] = None
                              ) -> Tuple[str, GenerationConfig, Optional[str]]:
        """
        Determines the effective model name, generation config, and system instruction.
        Priority:
        1. Session-specific base model (if provided and valid)
        2. Prompt's base_model_override (if prompt_config provided)
        3. Global default_base_model

        For generation parameters:
        1. Prompt's specific parameters (if prompt_config provided)
        2. Global default_generation_parameters
        """
        # Determine base model name
        model_name = self.default_base_model
        if prompt_config and prompt_config.base_model_override:
            model_name = prompt_config.base_model_override
        if session_base_model and session_base_model in self.gemini_global_settings.get("available_base_models", []):
            model_name = session_base_model

        # Determine generation parameters
        gen_params = self.default_gen_params_config.copy()  # Start with global defaults
        if prompt_config:
            if prompt_config.temperature is not None:
                gen_params["temperature"] = prompt_config.temperature
            if prompt_config.top_p is not None:
                gen_params["top_p"] = prompt_config.top_p
            if prompt_config.top_k is not None:
                gen_params["top_k"] = prompt_config.top_k
            if prompt_config.max_output_tokens is not None:
                gen_params["max_output_tokens"] = prompt_config.max_output_tokens

        generation_config = GenerationConfig(**gen_params)

        # System instruction
        system_instruction = prompt_config.system_instruction if prompt_config and prompt_config.system_instruction else None

        # log.debug(f"Effective Gemini Config: Model={model_name}, GenConfig={generation_config}, SysInstruction Present={bool(system_instruction)}")
        return model_name, generation_config, system_instruction

    def start_chat_session(self,
                           prompt_config: PromptModel,
                           session_base_model: Optional[str] = None,
                           serialized_history: Optional[List[Dict[str, Any]]] = None
                           ) -> Optional[genai.ChatSession]:
        """
        Starts a new Gemini ChatSession with the given prompt configuration,
        optional session-specific base model, and optional chat history.

        Args:
            prompt_config: The PromptModel object from the database.
            session_base_model: User's specific choice of base model for this session.
            serialized_history: Chat history deserialized from the database (list of dicts).

        Returns:
            A genai.ChatSession instance or None if configuration fails.
        """
        if not GEMINI_API_KEY:
            log.error("Cannot start chat session: GEMINI_API_KEY is not configured.")
            return None
        if not prompt_config:
            log.error("Cannot start chat session: prompt_config is required.")
            return None

        model_name, generation_config, system_instruction = self._get_effective_config(
            prompt_config=prompt_config,
            session_base_model=session_base_model
        )

        try:
            model_instance = genai.GenerativeModel(
                model_name=model_name,
                generation_config=generation_config,
                system_instruction=system_instruction,
                safety_settings=self.default_safety_settings
            )

            history_for_session = _deserialize_history(serialized_history)

            chat_session = model_instance.start_chat(history=history_for_session or [])  # Pass empty list if None
            log.info(
                f"Chat session started with model: {model_name}, prompt: '{prompt_config.name}'. History items: {len(history_for_session or [])}")
            return chat_session
        except Exception as e:
            log.error(
                f"Failed to initialize GenerativeModel or start chat for {model_name} with prompt '{prompt_config.name}': {e}",
                exc_info=True)
            return None

    async def send_message(self,
                           chat_session: genai.ChatSession,
                           message_text: str,
                           # TODO: Add support for sending images/other content parts
                           # message_parts: Optional[List[Any]] = None
                           ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        """
        Sends a message to an active ChatSession and gets the response.

        Args:
            chat_session: The active genai.ChatSession instance.
            message_text: The text content of the user's message.

        Returns:
            A tuple containing:
                - The bot's text response (str or None if error).
                - The updated chat history (list of dicts, serializable, or None if error).
        """
        if not chat_session:
            log.error("Cannot send message: chat_session is None.")
            return None, None

        if not GEMINI_API_KEY:  # Redundant if session creation checks, but good for safety
            log.error("Cannot send message: GEMINI_API_KEY is not configured.")
            return None, None

        try:
            # For streaming responses (as in your test/gemini_test.py):
            # response = await chat_session.send_message_async(message_text, stream=True)
            # full_text_response = ""
            # async for chunk in response:
            #     full_text_response += chunk.text
            # For non-streaming:
            response = await chat_session.send_message_async(message_text)

            bot_response_text = response.text

            # Prepare history for serialization
            # Convert Gemini Message objects to a list of dicts
            serializable_history = []
            if chat_session.history:
                for content_message in chat_session.history:  # content_message is of type ContentDict
                    parts_list = []
                    for part in content_message.parts:
                        # Assuming text parts for now.
                        # If you handle images/blobs, you'll need to serialize 'inline_data' or 'file_data'
                        parts_list.append({'text': part.text if hasattr(part, 'text') else ''})
                    serializable_history.append({'role': content_message.role, 'parts': parts_list})

            log.debug(f"Sent message, got response. History length: {len(chat_session.history)}")
            return bot_response_text, serializable_history

        except Exception as e:
            # Handle specific exceptions from the API if possible, e.g., BlockedPromptException
            # from google.generativeai.types import BlockedPromptException
            # if isinstance(e, BlockedPromptException):
            # log.warning(f"Message blocked by API for session. Reason: {e}")
            # return f"Response blocked by content safety policy. {e}", None # Or a generic message
            log.error(f"Error sending message or processing response: {e}", exc_info=True)
            return None, None  # Indicate error


# --- Example Usage (for testing this module directly) ---
if __name__ == '__main__':
    log.info("Testing GeminiService...")
    if not GEMINI_API_KEY:
        log.error("Cannot run tests: GEMINI_API_KEY is not set in .env or environment.")
        exit()


    # Mock PromptModel from database
    class MockPrompt:
        def __init__(self, name, system_instruction, temp=None, model_override=None):
            self.id = 1
            self.name = name
            self.system_instruction = system_instruction
            self.temperature = temp
            self.top_p = None
            self.top_k = None
            self.max_output_tokens = None
            self.base_model_override = model_override


    test_prompt = MockPrompt(
        name="Test Greeter",
        system_instruction="You are a friendly greeter. Always start your response with 'Aloha!'."
    )

    service = GeminiService()

    log.info("Attempting to start a new chat session...")
    session = service.start_chat_session(prompt_config=test_prompt)

    if session:
        log.info("Chat session started. Sending a message...")
        import asyncio


        async def run_send_message():
            response_text, updated_history = await service.send_message(session, "How are you today?")
            if response_text:
                log.info(f"Bot Response: {response_text}")
                log.info(f"Updated History (first 2 items): {updated_history[:2] if updated_history else 'None'}")
                assert "Aloha!" in response_text, "Response did not follow system instruction"
            else:
                log.error("Failed to get a response from the bot.")

            # Test with history
            log.info("\nAttempting to start a new chat session WITH history...")
            # Ensure history is in the correct dict format for _deserialize_history
            history_to_load = [
                {'role': 'user', 'parts': [{'text': 'Previous question'}]},
                {'role': 'model', 'parts': [{'text': 'Aloha! Previous answer.'}]}
            ]
            session_with_history = service.start_chat_session(prompt_config=test_prompt,
                                                              serialized_history=history_to_load)
            if session_with_history:
                log.info("Chat session with history started.")
                response_text_hist, _ = await service.send_message(session_with_history, "Another question?")
                if response_text_hist:
                    log.info(f"Bot Response (with history): {response_text_hist}")
                    assert "Aloha!" in response_text_hist
                else:
                    log.error("Failed to get a response (with history).")


        asyncio.run(run_send_message())
        log.info("GeminiService test completed.")
    else:
        log.error("Failed to start chat session.")