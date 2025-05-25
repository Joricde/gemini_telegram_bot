# gemini-telegram-bot/test_database.py

import os
import sys
import json  # For handling chat history serialization
from sqlalchemy.orm import Session

# Adjust an import path to ensure 'bot' package can be found if running script from root
# This assumes your project root is the parent directory of the 'bot' package.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from bot.database import engine, Base, SessionLocal, init_db
from bot.database import models as db_models  # Import all models to register them
from bot.database.crud import (
    get_or_create_user,
    create_prompt,
    get_prompt_by_name,
    get_prompt_by_id,
    create_or_update_chat_session_state,
    get_chat_session_state,
    get_deserialized_chat_history,
    get_group_setting,
    create_or_update_group_setting
)
from bot.utils import log  # Import our logger
from bot import DATABASE_URL, APP_CONFIG, PROMPTS_CONFIG  # Import loaded configurations


def clear_database():
    """Clears all data from tables and optionally drops/recreates them."""
    log.info("Clearing database...")
    # For SQLite, it's often easiest to just delete the DB file and recreate
    if DATABASE_URL.startswith("sqlite"):
        db_file_path = DATABASE_URL.split("sqlite:///./")[1]
        db_file_abs_path = os.path.join(project_root, db_file_path)
        if os.path.exists(db_file_abs_path):
            try:
                os.remove(db_file_abs_path)
                log.info(f"Deleted SQLite database file: {db_file_abs_path}")
            except OSError as e:
                log.error(f"Error deleting database file {db_file_abs_path}: {e}")
                return False
        # Re-initialize to create the file and tables again
        init_db()  # This will call Base.metadata.create_all(bind=engine)
        log.info("Database re-initialized (tables created).")
        return True
    else:
        # For other databases, you might drop and recreate tables
        # Base.metadata.drop_all(bind=engine)
        # Base.metadata.create_all(bind=engine)
        log.warning("Database clearing for non-SQLite not fully implemented in this script. Re-initializing tables.")
        init_db()
        return True


def initialize_system_prompts_from_config(db: Session):
    """Loads prompts from prompts.yml into the database if they don't exist."""
    log.info("Initializing system prompts from config...")
    default_gen_params = APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})
    default_base_model = APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash")

    for key, prompt_data in PROMPTS_CONFIG.items():
        prompt_name = prompt_data.get("name", key)
        existing_prompt = get_prompt_by_name(db, name=prompt_name)
        if not existing_prompt:
            created = create_prompt(
                db=db,
                name=prompt_name,
                description=prompt_data.get("description"),
                system_instruction=prompt_data.get("system_instruction", ""),
                temperature=prompt_data.get("temperature", default_gen_params.get("temperature")),
                top_p=prompt_data.get("top_p", default_gen_params.get("top_p")),
                top_k=prompt_data.get("top_k", default_gen_params.get("top_k")),
                max_output_tokens=prompt_data.get("max_output_tokens", default_gen_params.get("max_output_tokens")),
                base_model_override=prompt_data.get("base_model_override"),  # Can be None
                is_system_default=True  # Mark prompts from yml as system defaults
            )
            if created:
                log.info(f"Added system prompt to DB: '{prompt_name}' (ID: {created.id})")
            else:
                log.error(f"Failed to add system prompt to DB: '{prompt_name}'")
        # else:
        #     log.debug(f"System prompt '{prompt_name}' (ID: {existing_prompt.id}) already exists in DB.")


def run_tests():
    """Runs a series of database tests."""
    log.info("Starting database tests...")

    # --- Test 1: Database Initialization and Clearing ---
    if not clear_database():
        log.error("Database clearing failed. Aborting tests.")
        return
    log.info("Test 1.1: Database cleared and initialized successfully.")

    db = SessionLocal()  # Get a new session for tests
    try:
        # --- Test 1.2: Initialize System Prompts ---
        initialize_system_prompts_from_config(db)
        log.info("Test 1.2: System prompts initialization attempted.")

        # --- Test 2: User Creation and Retrieval ---
        log.info("--- Running User CRUD tests ---")
        test_user_id = "123456789"
        test_username = "testuser"
        user1 = get_or_create_user(db, user_id=test_user_id, username=test_username, first_name="Test",
                                   last_name="User")
        assert user1 is not None, "User creation failed"
        assert user1.user_id == test_user_id, f"User ID mismatch: expected {test_user_id}, got {user1.user_id}"
        log.info(f"Test 2.1: User '{user1.username}' created/retrieved with ID: {user1.user_id}")

        user1_retrieved = get_or_create_user(db, user_id=test_user_id, username="newusername")  # Test update
        assert user1_retrieved.username == "newusername", "User update failed"
        log.info(f"Test 2.2: User '{user1_retrieved.username}' info updated.")

        # --- Test 3: Prompt Retrieval (system prompts) ---
        log.info("--- Running Prompt Retrieval tests ---")
        lilith_prompt_name = PROMPTS_CONFIG.get("lilith_concise", {}).get("name", "莉莉丝 (毒舌大小姐)")
        prompt_lilith = get_prompt_by_name(db, name=lilith_prompt_name)
        assert prompt_lilith is not None, f"Prompt '{lilith_prompt_name}' not found after initialization."
        assert prompt_lilith.is_system_default is True, "System prompt not marked correctly."
        log.info(f"Test 3.1: System prompt '{prompt_lilith.name}' retrieved with ID: {prompt_lilith.id}")
        prompt_lilith_by_id = get_prompt_by_id(db, prompt_id=prompt_lilith.id)
        assert prompt_lilith_by_id is not None, "Prompt retrieval by ID failed."
        assert prompt_lilith_by_id.name == lilith_prompt_name, "Prompt name mismatch on ID retrieval."
        log.info(f"Test 3.2: System prompt '{prompt_lilith_by_id.name}' retrieved by ID successfully.")

        # --- Test 4: ChatSessionState Creation and Retrieval ---
        log.info("--- Running ChatSessionState CRUD tests ---")
        if not prompt_lilith:  # Ensure prompt_lilith was found
            log.error("Cannot run ChatSessionState tests, prerequisite prompt 'lilith_concise' not found.")
            return

        default_base_model = APP_CONFIG.get("gemini_settings", {}).get("default_base_model", "gemini-1.5-flash")

        # Mock chat history (list of dicts, as per simplified serialization)
        mock_history_initial = [
            {"role": "user", "parts": [{"text": "Hello Lilith"}]},
            {"role": "model", "parts": [{"text": "哼，有何贵干？"}]}
        ]

        # Test private chat session state
        session_private_chat_id = test_user_id  # For private chat, chat_id can be user_id
        session_state1 = create_or_update_chat_session_state(
            db,
            telegram_chat_id=session_private_chat_id,
            telegram_user_id=test_user_id,  # User specific
            active_prompt_id=prompt_lilith.id,
            current_base_model=default_base_model,
            gemini_chat_history=mock_history_initial
        )
        assert session_state1 is not None, "ChatSessionState creation failed for private chat."
        assert session_state1.active_prompt_id == prompt_lilith.id
        assert session_state1.current_base_model == default_base_model
        log.info(
            f"Test 4.1: ChatSessionState created for private chat {session_private_chat_id} (ID: {session_state1.id})")

        retrieved_history1 = get_deserialized_chat_history(session_state1)
        assert retrieved_history1 is not None, "Failed to deserialize history for session_state1"
        assert len(retrieved_history1) == len(mock_history_initial), "History length mismatch"
        assert retrieved_history1[0]["role"] == "user"
        log.info(f"Test 4.2: Chat history deserialized correctly for private chat session: {retrieved_history1}")

        # Test updating the session with new history
        mock_history_updated = mock_history_initial + [
            {"role": "user", "parts": [{"text": "Tell me a joke."}]}
        ]
        session_state1_updated = create_or_update_chat_session_state(
            db,
            telegram_chat_id=session_private_chat_id,
            telegram_user_id=test_user_id,
            active_prompt_id=prompt_lilith.id,  # Assuming same prompt
            current_base_model="gemini-1.5-pro",  # Change model
            gemini_chat_history=mock_history_updated
        )
        assert session_state1_updated.id == session_state1.id, "Session update should not create new row"
        assert session_state1_updated.current_base_model == "gemini-1.5-pro", "Base model update failed"
        retrieved_history_updated = get_deserialized_chat_history(session_state1_updated)
        assert len(retrieved_history_updated) == len(mock_history_updated), "Updated history length mismatch"
        log.info(f"Test 4.3: ChatSessionState updated with new history and model for private chat.")

        # Test shared group chat session state
        group_chat_id = "group123"
        # First, ensure group setting exists (though not strictly required by ChatSessionState model directly)
        create_or_update_group_setting(db, group_id=group_chat_id, shared_mode_prompt_id=prompt_lilith.id)

        session_group_shared = create_or_update_chat_session_state(
            db,
            telegram_chat_id=group_chat_id,
            telegram_user_id=None,  # For shared group session, user_id is None
            active_prompt_id=prompt_lilith.id,
            current_base_model=default_base_model,
            gemini_chat_history=[{"role": "user", "parts": [{"text": "Group question"}]}]
        )
        assert session_group_shared is not None, "ChatSessionState creation failed for shared group chat."
        assert session_group_shared.telegram_user_id is None, "User ID should be None for shared group session."
        log.info(
            f"Test 4.4: ChatSessionState created for shared group chat {group_chat_id} (ID: {session_group_shared.id})")

        retrieved_group_session = get_chat_session_state(db, telegram_chat_id=group_chat_id, telegram_user_id=None)
        assert retrieved_group_session is not None, "Failed to retrieve shared group session."
        assert retrieved_group_session.id == session_group_shared.id
        log.info(f"Test 4.5: Shared group session retrieved successfully.")

        # --- Test 5: GroupSetting CRUD ---
        log.info("--- Running GroupSetting CRUD tests ---")
        test_group_id = "987654"
        group_setting1 = create_or_update_group_setting(
            db,
            group_id=test_group_id,
            default_mode="shared",
            shared_mode_prompt_id=prompt_lilith.id,
            random_reply_enabled=True
        )
        assert group_setting1 is not None, "GroupSetting creation failed"
        assert group_setting1.default_mode == "shared"
        log.info(f"Test 5.1: GroupSetting created for group {test_group_id} with mode 'shared'.")

        group_setting_updated = create_or_update_group_setting(
            db,
            group_id=test_group_id,
            default_mode="individual",
            random_reply_enabled=False
        )
        assert group_setting_updated.default_mode == "individual", "GroupSetting mode update failed"
        assert group_setting_updated.random_reply_enabled is False, "GroupSetting random reply update failed"
        assert group_setting_updated.shared_mode_prompt_id == prompt_lilith.id, "shared_mode_prompt_id should persist if not updated"
        log.info(f"Test 5.2: GroupSetting updated for group {test_group_id} to mode 'individual'.")

        retrieved_group_setting = get_group_setting(db, group_id=test_group_id)
        assert retrieved_group_setting is not None, "Failed to retrieve group setting."
        assert retrieved_group_setting.default_mode == "individual"
        log.info(f"Test 5.3: GroupSetting retrieved successfully for group {test_group_id}.")

        log.info("All database tests completed successfully.")

    except AssertionError as e:
        log.error(f"Assertion Error during tests: {e}", exc_info=True)
    except Exception as e:
        log.error(f"An unexpected error occurred during tests: {e}", exc_info=True)
    finally:
        db.close()
        log.info("Database session closed.")


if __name__ == "__main__":
    # Ensure the data directory exists for SQLite, defined by DATABASE_URL in .env
    # Example: if DATABASE_URL="sqlite:///./data/bot.db"
    data_dir = os.path.join(project_root, "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        log.info(f"Created data directory: {data_dir}")

    run_tests()