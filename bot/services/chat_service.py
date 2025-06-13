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

    async def _get_system_prompt(self, user_id: int, is_group: bool) -> str:
        """
        Determines the correct system prompt based on context (group vs. private)
        and user settings (active custom prompt). Implements the "header/payload" logic.
        """
        # 1. Determine the Payload (the core persona)
        payload = ""
        active_custom_prompt = self.prompt_service.get_available_prompts()
        if active_custom_prompt:
            payload = active_custom_prompt.prompt_text
            logger.debug(f"Using active custom prompt '{active_custom_prompt.title}' for user {user_id}.")
        else:
            # Fallback to the default prompt from prompts.yml
            payload = settings.prompts.get('default', {}).get('prompt', "You are a helpful assistant.")
            logger.debug(f"Using default prompt for user {user_id}.")

        # 2. Determine the Header (context-specific instructions)
        if is_group:
            header = settings.app.telegram_bot.group_chat_header
            return f"{header}\n\n{payload}"

        return payload

    async def handle_private_message(self, user_data: telegram.User, text: str) -> str:
        """
        Handles an incoming message from a private chat.
        """
        # Ensure user exists in DB
        crud.get_or_create_user(db=self.db, user_data=user_data)

        # Get or create the chat session for the user
        session = crud.get_or_create_session(db=self.db, chat_id=user_data.id)

        # Check for session timeout
        timeout_delta = timedelta(seconds=settings.app.telegram_bot.session_timeout_seconds)
        if datetime.now(timezone.utc) - session.last_interaction_at.replace(tzinfo=timezone.utc) > timeout_delta:
            logger.info(f"Session timed out for user {user_data.id}. Resetting history.")
            session = crud.reset_session(db=self.db, chat_id=user_data.id)
            # Optionally, send a notification message. We'll add this logic in the handler.

        history = session.history.copy() if session.history else []

        # Get the appropriate system prompt
        system_prompt = await self._get_system_prompt(user_id=user_data.id, is_group=False)

        # Generate AI response
        ai_response = await self.gemini_service.generate_response_async(
            system_prompt=system_prompt,
            history=history,
            user_prompt=text
        )

        if not ai_response:
            ai_response = "I'm sorry, I couldn't come up with a response."

        # Update history and save session
        history.append({"role": "user", "parts": text})
        history.append({"role": "assistant", "parts": ai_response})
        crud.update_session(db=self.db, chat_id=user_data.id, new_history=history)

        return ai_response

    async def handle_group_message(self, chat_id: int, user_data: telegram.User, text: str, is_mention: bool) -> \
    Optional[str]:
        """
        Handles an incoming message from a group chat.
        """
        # Ensure user and session exist
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

        # Format the message with username for group context
        formatted_text = f"{user_data.first_name}: {text}"
        history = session.history.copy() if session.history else []
        history.append({"role": "user", "parts": formatted_text})

        if should_reply:
            system_prompt = await self._get_system_prompt(user_id=user_data.id, is_group=True)

            # Generate response using the group context
            ai_response = await self.gemini_service.generate_response_async(
                system_prompt=system_prompt,
                history=history,  # Pass the history that includes the new formatted message
                user_prompt=""  # The prompt is already in the history, so we send an empty prompt here
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
