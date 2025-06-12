# gemini-telegram-bot/bot/database/models.py

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import datetime
import enum

from . import Base  # From bot.database.__init__


# Enum for Prompt Types
class PromptType(enum.Enum):
    PRIVATE = "private"
    GROUP_ROLE_PAYLOAD = "group_role_payload"


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)
    username = Column(String, nullable=True, index=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    prompts_created = relationship("Prompt", back_populates="creator")
    # chat_sessions = relationship("ChatSessionState", back_populates="user") # Defined in ChatSessionState


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    creator_user_id = Column(String, ForeignKey("users.user_id"), nullable=True,
                             index=True)  # Nullable for system prompts
    name = Column(String, nullable=False,
                  index=True)  # Not globally unique, but should be unique per user for their created prompts

    prompt_type = Column(SAEnum(PromptType), nullable=False, default=PromptType.PRIVATE, index=True)

    description = Column(String, nullable=True)  # Optional description
    system_instruction = Column(Text,
                                nullable=False)  # For "private" type, this is the full instruction. For "group_role_payload", this is the payload.

    temperature = Column(Float, nullable=True)
    top_p = Column(Float, nullable=True)
    top_k = Column(Integer, nullable=True)
    max_output_tokens = Column(Integer, nullable=True)
    base_model_override = Column(String, nullable=True)

    is_system_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    creator = relationship("User", back_populates="prompts_created")

    # Relationship for GroupSetting pointing to a shared mode role prompt
    # group_settings_shared_role = relationship("GroupSetting", foreign_keys="[GroupSetting.shared_mode_role_prompt_id]", back_populates="shared_mode_role_prompt_detail")


class GroupSetting(Base):
    __tablename__ = "group_settings"

    group_id = Column(String, primary_key=True, index=True)
    current_mode = Column(String, default="individual", nullable=False)  # "individual" or "shared"

    # Points to a Prompt of type GROUP_ROLE_PAYLOAD
    shared_mode_role_prompt_id = Column(Integer, ForeignKey("prompts.id"), nullable=True)
    random_reply_enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    shared_mode_role_prompt_detail = relationship(
        "Prompt")  # , foreign_keys=[shared_mode_role_prompt_id], back_populates="group_settings_shared_role")


class ChatSessionState(Base):
    __tablename__ = "chat_session_states"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    telegram_chat_id = Column(String, nullable=False, index=True)  # Private chat_id or group_id
    telegram_user_id = Column(String, ForeignKey("users.user_id"), nullable=True,
                              index=True)  # User's ID in private or group-individual mode. Null for group-shared mode.

    # For private/individual modes, this points to a "private" type Prompt.
    # For group shared mode, this session might not directly use a prompt_id if the role is purely from GroupSetting,
    # or it could point to a generic/base prompt if needed. Let's assume for now that active_prompt_id is for the main "interacting" prompt.
    active_prompt_id = Column(Integer, ForeignKey("prompts.id"), nullable=False)
    current_base_model = Column(String, nullable=False)
    gemini_chat_history = Column(Text, nullable=True)  # JSON serialized

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_interaction_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")  # , back_populates="chat_sessions")
    active_prompt = relationship("Prompt")


class GroupMessageCache(Base):
    __tablename__ = "group_message_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(String, ForeignKey("group_settings.group_id"), nullable=False, index=True)
    message_id = Column(String, nullable=False)  # Telegram message ID
    user_id = Column(String, ForeignKey("users.user_id"), nullable=True)
    username = Column(String, nullable=True)
    text = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Adding unique constraint for message_id within a group_id
    # __table_args__ = (UniqueConstraint('group_id', 'message_id', name='uq_group_message'),)

    group = relationship("GroupSetting")
    author = relationship("User")