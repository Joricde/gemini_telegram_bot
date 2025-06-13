# bot/database/models.py
import datetime
from datetime import timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime, # Important: We use DateTime from sqlalchemy
    Text,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Represents a Telegram user."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=False)
    username = Column(String, unique=True, nullable=True)
    first_name = Column(String)
    # last_name = Column(String, nullable=True)
    # is_bot = Column(Boolean, default=False)
    # language_code = Column(String, nullable=True)

    # CORRECTED: Added timezone=True
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc), onupdate=lambda: datetime.datetime.now(timezone.utc))

    prompts = relationship("Prompt", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Prompt(Base):
    """Represents a user-defined prompt/persona."""
    __tablename__ = "prompts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Creator of the prompt
    title = Column(String, nullable=False)
    prompt_text = Column(Text, nullable=False)
    # is_active = Column(Boolean, default=False) # <--- 关键：删除这一行

    user = relationship("User", back_populates="prompts")

    def __repr__(self):
        return f"<Prompt(id={self.id}, title='{self.title}')>"

class ChatSessionState(Base):
    """Represents the state of a conversation session."""
    __tablename__ = "chat_session_states"

    id = Column(Integer, primary_key=True, index=True)
    # This ID can be a user_id for private chats or a group_id for group chats.
    chat_id = Column(Integer, unique=True, nullable=False, index=True)
    history = Column(JSON, nullable=False, default=list)
    # This key will store values like 'yaml:default' or 'db:123'
    active_prompt_key = Column(String, nullable=False, default="yaml:default") # <--- 关键：我们将使用此字段
    messages_since_last_reply = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))
    last_interaction_at = Column(DateTime(timezone=True), default=lambda: datetime.datetime.now(timezone.utc))

    def __repr__(self):
        return f"<ChatSessionState(chat_id={self.chat_id}, active_prompt_key='{self.active_prompt_key}')>"