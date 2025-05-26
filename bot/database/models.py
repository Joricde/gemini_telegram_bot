# gemini-telegram-bot/bot/database/models.py

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func  # 用于设置默认时间戳
import datetime

from . import Base  # 从同目录下的 __init__.py 导入 Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)  # Telegram User ID (通常是整数，但字符串更灵活)
    username = Column(String, nullable=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships (可选，但有助于 ORM 操作)
    prompts_created = relationship("Prompt", back_populates="creator")
    # Removed direct back_populates from here to ChatSessionState to avoid circularity if ChatSessionState
    # needs to be more flexible with its user relationship (e.g. if user_id could be nullable for system sessions)
    # chat_sessions = relationship("ChatSessionState", back_populates="user")


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    creator_user_id = Column(String, ForeignKey("users.user_id"), nullable=True)  # Nullable for system prompts
    name = Column(String, index=True, nullable=False, unique=True)  # Prompt name should be unique
    description = Column(String, nullable=True)
    system_instruction = Column(Text, nullable=False)

    # Persona-specific overrides for generation parameters
    temperature = Column(Float, nullable=True)
    top_p = Column(Float, nullable=True)
    top_k = Column(Integer, nullable=True)
    max_output_tokens = Column(Integer, nullable=True)

    # Persona-specific override for base model
    base_model_override = Column(String, nullable=True)

    is_system_default = Column(Boolean, default=False)  # Is this a pre-defined system prompt?
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())  # Default now() for creation

    # Relationships
    creator = relationship("User", back_populates="prompts_created")


class GroupSetting(Base):
    __tablename__ = "group_settings"

    group_id = Column(String, primary_key=True, index=True)  # Telegram Group ID
    default_mode = Column(String, default="individual", nullable=False)  # "individual" or "shared"

    shared_mode_prompt_id = Column(Integer, ForeignKey("prompts.id"), nullable=True)
    random_reply_enabled = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship to the prompt used in shared mode
    shared_mode_prompt = relationship("Prompt")


class ChatSessionState(Base):
    __tablename__ = "chat_session_states"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # For private chats, telegram_chat_id = telegram_user_id
    # For group individual mode, telegram_chat_id = group_id, telegram_user_id = user's ID
    # For group shared mode, telegram_chat_id = group_id, telegram_user_id = None (or a special bot ID)
    telegram_chat_id = Column(String, nullable=False, index=True)
    telegram_user_id = Column(String, ForeignKey("users.user_id"), nullable=True, index=True)

    active_prompt_id = Column(Integer, ForeignKey("prompts.id"), nullable=False)
    current_base_model = Column(String, nullable=False)  # e.g., "gemini-1.5-flash"

    gemini_chat_history = Column(Text, nullable=True)  # JSON serialized history

    # New column to mark the active session for a user/chat
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    last_interaction_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User") # No back_populates needed if User model doesn't link back directly here for this use case
    active_prompt = relationship("Prompt")


class GroupMessageCache(Base):
    __tablename__ = "group_message_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(String, ForeignKey("group_settings.group_id"), nullable=False, index=True)
    message_id = Column(String, nullable=False, unique=True)  # Telegram message ID, unique within a group
    user_id = Column(String, ForeignKey("users.user_id"),
                     nullable=True)  # Can be null if user not in our DB or system message
    username = Column(String, nullable=True)  # Telegram username
    text = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.datetime.now(datetime.timezone.utc)) # Ensure UTC now

    # Relationships
    group = relationship("GroupSetting")
    author = relationship("User")