# bot/services/gemini_service.py
import asyncio
from typing import List, Dict, Any, Optional

from google import genai
from google.genai import types as genai_types
from google.genai.types import HarmCategory
from google.generativeai.types import HarmBlockThreshold

from bot.core.config import settings
from bot.core.logging import logger


class GeminiService:
    """
    A service class to encapsulate all interactions with the Google Gemini API.
    It follows the new `google-genai` library's patterns.
    """

    def __init__(self):
        """
        Initializes the Gemini client using the API key from settings.
        """
        if not settings.gemini_api_key:
            logger.critical("GEMINI_API_KEY is not configured. GeminiService will not function.")
            self.client = None
            return

        self.client = genai.Client(api_key=settings.gemini_api_key)
        logger.info("GeminiService initialized successfully.")

    def _format_history(self, history: List[Dict[str, Any]]) -> List[genai_types.Content]:
        """
        Converts our internal chat history format to the format required by the google-genai library.

        Args:
            history: A list of dictionaries, e.g., [{"role": "user", "parts": "Hello"}]

        Returns:
            A list of genai_types.Content objects.
        """
        formatted_history = []
        for item in history:
            role = item.get("role")
            parts_text = item.get("parts")
            # The API expects role to be 'user' or 'model'.
            # We ensure consistency here.
            if role == "assistant":
                role = "model"

            if role in ["user", "model"] and parts_text:
                formatted_history.append(
                    genai_types.Content(role=role, parts=[genai_types.Part.from_text(text=parts_text)]))
        return formatted_history

    async def generate_response_async(
            self,
            system_prompt: str,
            history: List[Dict[str, Any]],
            user_prompt: str
    ) -> Optional[str]:
        """
        Generates a response from the Gemini API asynchronously.

        Args:
            system_prompt: The system instruction for the model.
            history: The conversation history.
            user_prompt: The latest user message to respond to.

        Returns:
            The generated text response as a string, or None if an error occurs.
        """
        if not self.client:
            logger.error("Gemini client is not initialized. Cannot generate response.")
            return "Error: AI service is not configured."

        try:
            # Format history and add the new user prompt
            full_contents = self._format_history(history)
            full_contents.append(genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=user_prompt)]))

            # Define safety settings to be less restrictive
            # safety_settings = [
            #     genai_types.SafetySettingDict(
            #         category=HarmCategory.HARM_CATEGORY_HARASSMENT,
            #         threshold=HarmBlockThreshold.BLOCK_NONE
            #     ),
            #     genai_types.SafetySetting(
            #         category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            #         threshold=HarmBlockThreshold.BLOCK_NONE
            #     ),
            #     genai_types.SafetySetting(
            #         category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            #         threshold=HarmBlockThreshold.BLOCK_NONE
            #     ),
            #     genai_types.SafetySetting(
            #         category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            #         threshold=HarmBlockThreshold.BLOCK_NONE
            #     ),
            # ]

            # 3. Create the generation configuration, NOW WITH safety_settings INSIDE
            generation_config = genai_types.GenerateContentConfig(
                system_instruction=[genai_types.Part.from_text(text=system_prompt)],
                # safety_settings=safety_settings  # <-- MOVED TO THE CORRECT LOCATION
            )

            logger.debug(f"Sending request to Gemini with model: {settings.app.gemini.model_name}")

            # 4. Run the synchronous API call in a separate thread
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=settings.app.gemini.model_name,
                contents=full_contents,
                config=generation_config,
                # No safety_settings argument here anymore
            )

            # 5. Extract and return the text from the response
            if response and response.text:
                return response.text
            else:
                logger.warning("Gemini API returned an empty response.")
                if response.prompt_feedback:
                    logger.warning(f"Prompt feedback: {response.prompt_feedback}")
                    return f"I couldn't respond to that. It might have triggered my safety filters. (Reason: {response.prompt_feedback.block_reason.name})"
                return None

        except Exception as e:
            logger.error(f"An error occurred while generating Gemini response: {e}", exc_info=True)
            return "I'm sorry, an error occurred while I was thinking."
