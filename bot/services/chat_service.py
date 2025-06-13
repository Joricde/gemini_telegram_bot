# bot/services/chat_service.py
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
import telegram

from bot.core.config import settings
from bot.core.logging import logger
from bot.database import crud
from bot.services.gemini_service import GeminiService
from bot.services.prompt_service import PromptService


class ChatService:
    """
    The central service for handling all chat-related business logic.
    It orchestrates interactions between the database, the Gemini API, and other services.
    """

    def __init__(self, db: Session, gemini_service: GeminiService, prompt_service: PromptService):
        """
        Initializes the ChatService with its dependencies.

        Args:
            db: An active SQLAlchemy Session.
            gemini_service: An instance of GeminiService.
            prompt_service: An instance of PromptService.
        """
        self.db = db
        self.gemini_service = gemini_service
        self.prompt_service = prompt_service
        logger.info("ChatService initialized.")

    async def _get_system_prompt(self, chat_id: int, is_group: bool) -> str:
        """
        Determines the correct system prompt based on the session's active_prompt_key.
        """
        # 1. Get the session to find out which prompt is active for THIS chat.
        session = crud.get_or_create_session(db=self.db, chat_id=chat_id)
        active_key = session.active_prompt_key
        logger.debug(f"Chat {chat_id} is using active prompt key: '{active_key}'")

        # 2. Use the PromptService to get the text for that key (the "payload")
        payload = self.prompt_service.get_prompt_text_by_key(active_key)

        # Fallback if the key points to a deleted/invalid prompt
        if not payload:
            logger.warning(f"Could not resolve prompt key '{active_key}'. Falling back to default.")
            payload = self.prompt_service.get_prompt_text_by_key("yaml:default")
            # Also reset the session's key to the valid default
            crud.set_active_prompt_key_for_session(db=self.db, chat_id=chat_id, prompt_key="yaml:default")

        # 3. Determine the Header (context-specific instructions)
        header = ""
        if is_group:
            header = settings.app.telegram_bot.group_chat_header

        # Combine header and payload
        return f"{header}\n\n{payload}".strip()

    async def handle_private_message(self, user_data: telegram.User, text: str) -> str:
        """
        Handles an incoming message from a private chat.
        """
        chat_id = user_data.id  # In private chat, chat_id is the user_id
        crud.get_or_create_user(db=self.db, user_data=user_data)
        session = crud.get_or_create_session(db=self.db, chat_id=chat_id)

        # ... (session timeout logic is fine) ...

        history = session.history.copy() if session.history else []

        # Get the appropriate system prompt for THIS chat session
        system_prompt = await self._get_system_prompt(chat_id=chat_id, is_group=False)

        # ... (the rest of the function is mostly fine, just ensure chat_id is used consistently) ...
        ai_response = await self.gemini_service.generate_response_async(
            system_prompt=system_prompt,
            history=history,
            user_prompt=text
        )

        if not ai_response:
            ai_response = "I'm sorry, I couldn't come up with a response."

        history.append({"role": "user", "parts": text})
        history.append({"role": "assistant", "parts": ai_response})
        crud.update_session(db=self.db, chat_id=chat_id, new_history=history)

        return ai_response

    async def handle_group_message(self, chat_id: int, user_data: telegram.User, text: str, is_mention: bool) -> Optional[str]:
        """
        Handles an incoming message from a group chat.
        """
        crud.get_or_create_user(db=self.db, user_data=user_data)
        session = crud.get_or_create_session(db=self.db, chat_id=chat_id)

        # Decide whether to reply
        should_reply = False
        if is_mention:
            should_reply = True
            logger.info(f"Bot was mentioned in group {chat_id}. Replying.")
        elif random.random() < settings.app.telegram_bot.group_reply_probability:
            should_reply = True
            logger.info(f"Probabilistic reply triggered in group {chat_id}.")

        formatted_text = f"{user_data.first_name}: {text}"
        history = session.history.copy() if session.history else []
        history.append({"role": "user", "parts": formatted_text})

        if should_reply:
            # Correctly get the prompt for THIS group chat
            system_prompt = await self._get_system_prompt(chat_id=chat_id, is_group=True)

            ai_response = await self.gemini_service.generate_response_async(
                system_prompt=system_prompt,
                history=history,
                user_prompt=""
            )

            if not ai_response:
                # Don't save history if AI fails to respond
                return None

            history.append({"role": "assistant", "parts": ai_response})
            # Reset the counter since we replied
            crud.update_session(db=self.db, chat_id=chat_id, new_history=history, messages_since_reply=0)
            return ai_response
        else:
            # Not replying, just update history and increment counter
            new_counter = (session.messages_since_last_reply or 0) + 1
            crud.update_session(db=self.db, chat_id=chat_id, new_history=history, messages_since_reply=new_counter)
            return None
