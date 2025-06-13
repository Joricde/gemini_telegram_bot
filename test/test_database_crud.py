# tests/test_database_crud.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import telegram

from bot.database.models import Base
from bot.database import crud

# Use an in-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

# Create a testing engine and session
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Pytest Fixture: A function that sets up resources for tests.
# This fixture will run before each test function that uses it.
@pytest.fixture()
def db_session():
    """
    Pytest fixture to create a new database session for each test.
    It creates all tables, yields the session, and then drops all tables after the test.
    """
    # Create the tables in the in-memory database
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop all tables to ensure a clean state for the next test
        Base.metadata.drop_all(bind=engine)


# --- Our Tests Begin Here ---

def test_get_or_create_user(db_session):
    """
    Tests creating a new user and retrieving an existing one.
    """
    # Create a mock telegram.User object
    mock_user_data = telegram.User(
        id=12345,
        first_name="Test",
        is_bot=False,
        username="testuser"
    )

    # 1. Test creation
    user = crud.get_or_create_user(db=db_session, user_data=mock_user_data)
    assert user is not None
    assert user.id == 12345
    assert user.username == "testuser"
    assert user.first_name == "Test"

    # 2. Test retrieval
    user_retrieved = crud.get_or_create_user(db=db_session, user_data=mock_user_data)
    assert user_retrieved is not None
    assert user_retrieved.id == user.id  # Should be the same user

    # 3. Test update
    mock_user_data_updated = telegram.User(
        id=12345,
        first_name="Test Updated",
        is_bot=False,
        username="testuser_new"
    )
    user_updated = crud.get_or_create_user(db=db_session, user_data=mock_user_data_updated)
    assert user_updated.id == 12345
    assert user_updated.first_name == "Test Updated"
    assert user_updated.username == "testuser_new"


def test_create_and_get_prompts(db_session):
    """
    Tests creating and retrieving prompts for a user.
    """
    # First, we need a user to own the prompts
    mock_user_data = telegram.User(id=54321, first_name="PromptOwner", is_bot=False)
    user = crud.get_or_create_user(db=db_session, user_data=mock_user_data)

    # 1. Test prompt creation
    prompt1 = crud.create_user_prompt(db=db_session, user_id=user.id, title="Test Prompt 1", text="This is text 1.")
    assert prompt1 is not None
    assert prompt1.title == "Test Prompt 1"
    assert prompt1.user_id == user.id

    prompt2 = crud.create_user_prompt(db=db_session, user_id=user.id, title="Test Prompt 2", text="This is text 2.")
    assert prompt2 is not None

    # 2. Test retrieving all prompts for the user
    user_prompts = crud.get_user_prompts(db=db_session, user_id=user.id)
    assert len(user_prompts) == 2
    assert user_prompts[0].title == "Test Prompt 1"


def test_session_management(db_session):
    """
    Tests creating and updating a chat session.
    """
    chat_id = 98765

    # 1. Test session creation
    session = crud.get_or_create_session(db=db_session, chat_id=chat_id)
    assert session is not None
    assert session.chat_id == chat_id
    assert session.history == []
    assert session.messages_since_last_reply == 0

    # 2. Test session retrieval
    session_retrieved = crud.get_or_create_session(db=db_session, chat_id=chat_id)
    assert session_retrieved.id == session.id

    # 3. Test session update
    new_history = [{"role": "user", "parts": "Hello"}]
    crud.update_session(db=db_session, chat_id=chat_id, new_history=new_history, messages_since_reply=1)

    session_updated = crud.get_session(db=db_session, chat_id=chat_id)
    assert session_updated.history[0]["parts"] == "Hello"
    assert session_updated.messages_since_last_reply == 1