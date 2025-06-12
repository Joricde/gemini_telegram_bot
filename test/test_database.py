# gemini-telegram-bot/test/test_database.py

import os
import sys
import json
from sqlalchemy.orm import Session
import datetime  # For GroupMessageCache timestamp

# Adjust an import path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # Points to gemini_telegram_bot-dev
sys.path.insert(0, project_root)

from bot.database import engine, Base, SessionLocal, init_db
from bot.database import models as db_models
from bot.database.models import PromptType  # Import the Enum
from bot.database.crud import (
    get_or_create_user,
    create_prompt,
    get_prompt_by_id,
    get_prompt_by_id_and_user,
    get_prompts_by_user_and_type,
    get_system_default_prompts,
    get_system_prompt_by_name,  # Added
    update_prompt_instruction,
    delete_prompt,
    create_or_update_group_setting,
    get_group_setting,
    create_new_chat_session,
    get_active_chat_session_state,
    update_chat_history,
    get_deserialized_chat_history,
    add_message_to_cache,
    get_recent_messages_from_cache
)
from bot.utils import log
from bot import DATABASE_URL, APP_CONFIG, PROMPTS_CONFIG, PROJECT_ROOT as BOT_PROJECT_ROOT


# In test/test_database.py

def clear_database():
    """Clears all data from tables and optionally drops/recreates them."""
    log.info("Clearing database...")
    # BOT_PROJECT_ROOT is imported from bot as PROJECT_ROOT
    # DATABASE_URL is imported from bot

    log.debug(f"DATABASE_URL used by test: {DATABASE_URL}")
    log.debug(f"BOT_PROJECT_ROOT used by test: {BOT_PROJECT_ROOT}")

    if DATABASE_URL.startswith("sqlite:///"):
        # Extract the absolute file path from the DATABASE_URL
        # e.g., "sqlite:///C:/path/to/project/data/bot.db" -> "C:/path/to/project/data/bot.db"
        # e.g., "sqlite:////path/to/project/data/bot.db" -> "/path/to/project/data/bot.db" (for Unix-like)
        db_file_abs_path = DATABASE_URL[len("sqlite:///"):]
        if os.name == 'posix' and DATABASE_URL.startswith(
                "sqlite:////"):  # Handle Unix-style absolute path with 4 slashes
            db_file_abs_path = "/" + db_file_abs_path

        log.debug(f"Absolute path to DB file determined as: {db_file_abs_path}")

        # Determine the directory for the database file
        db_dir = os.path.dirname(db_file_abs_path)
        log.debug(f"Directory for DB file determined as: {db_dir}")

        # Ensure this directory exists
        if not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                log.info(f"Created database directory: {db_dir}")
            except OSError as e:
                log.error(f"Failed to create database directory {db_dir}: {e}")
                return False  # Cannot proceed if directory can't be created

        # If the database file exists, try to remove it
        if os.path.exists(db_file_abs_path):
            try:
                os.remove(db_file_abs_path)
                log.info(f"Deleted SQLite database file: {db_file_abs_path}")
            except OSError as e:
                log.error(f"Error deleting database file {db_file_abs_path}: {e}")
                return False  # If deletion fails, init_db might have issues

        # Now, initialize the database (which should create the file and tables)
        # init_db() uses the SQLAlchemy engine, which is configured with DATABASE_URL.
        try:
            init_db()
            log.info("Database re-initialized (tables created via init_db).")
            # Verify the file was created by init_db()
            if not os.path.exists(db_file_abs_path):
                log.error(f"Database file {db_file_abs_path} was NOT created by init_db() even after successful call.")
                return False
            log.info(f"Database file {db_file_abs_path} confirmed to exist after init_db().")

        except Exception as e:
            log.error(f"Error during init_db(): {e}", exc_info=True)
            return False

        return True
    else:
        log.warning(f"DATABASE_URL '{DATABASE_URL}' is not a recognized SQLite URL. Skipping SQLite-specific clear.")
        # For other databases, you might drop and recreate tables
        # Base.metadata.drop_all(bind=engine)
        # Base.metadata.create_all(bind=engine)
        try:
            init_db()  # Attempt to initialize anyway for other DB types
            log.info("Database re-initialized for non-SQLite (tables created if supported).")
            return True
        except Exception as e:
            log.error(f"Error during init_db() for non-SQLite: {e}", exc_info=True)
            return False

def initialize_system_prompts_from_config(db: Session):
    """Loads prompts from prompts.yml into the database if they don't exist."""
    log.info("Initializing system prompts from config...")
    default_gen_params = APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})

    for key, prompt_data in PROMPTS_CONFIG.items():
        prompt_name = prompt_data.get("name", key)
        # Get prompt_type from YML, default to PRIVATE if not specified for backward compatibility in test
        prompt_type_str = prompt_data.get("prompt_type", "private").upper()
        try:
            prompt_type_enum = PromptType[prompt_type_str]
        except KeyError:
            log.warning(
                f"Invalid prompt_type '{prompt_type_str}' for '{prompt_name}' in prompts.yml. Defaulting to PRIVATE.")
            prompt_type_enum = PromptType.PRIVATE

        existing_prompt = get_system_prompt_by_name(db,
                                                    name=prompt_name)  # Check if system prompt with this name exists
        if not existing_prompt:
            created = create_prompt(
                db=db,
                name=prompt_name,
                description=prompt_data.get("description"),
                system_instruction=prompt_data.get("system_instruction", ""),
                prompt_type=prompt_type_enum,  # Use the enum
                temperature=prompt_data.get("temperature", default_gen_params.get("temperature")),
                top_p=prompt_data.get("top_p", default_gen_params.get("top_p")),
                top_k=prompt_data.get("top_k", default_gen_params.get("top_k")),
                max_output_tokens=prompt_data.get("max_output_tokens", default_gen_params.get("max_output_tokens")),
                base_model_override=prompt_data.get("base_model_override"),
                is_system_default=True  # Mark prompts from yml as system defaults
            )
            if created:
                log.info(
                    f"Added system prompt to DB: '{prompt_name}' (Type: {prompt_type_enum.value}, ID: {created.id})")
            else:
                log.error(f"Failed to add system prompt to DB: '{prompt_name}'")


def run_tests():
    log.info("Starting database tests...")

    if not clear_database():
        log.error("Database clearing failed. Aborting tests.")
        return
    log.info("Test 0: Database cleared and initialized successfully.")

    db = SessionLocal()
    try:
        # --- Test 0.1: Initialize System Prompts ---
        initialize_system_prompts_from_config(db)
        log.info("Test 0.1: System prompts initialization attempted.")

        # --- Test 1: User CRUD ---
        log.info("--- Running User CRUD tests ---")
        test_user_id = "user123"
        user1 = get_or_create_user(db, user_id=test_user_id, username="testuser", first_name="Test", last_name="User")
        assert user1 is not None, "User creation failed"
        assert user1.user_id == test_user_id
        log.info(f"Test 1.1: User '{user1.username}' created/retrieved.")

        user1_updated = get_or_create_user(db, user_id=test_user_id, username="testuser_updated")
        assert user1_updated.username == "testuser_updated"
        log.info(f"Test 1.2: User '{user1_updated.username}' updated.")

        # --- Test 2: Prompt CRUD ---
        log.info("--- Running Prompt CRUD tests ---")
        # 2.1 Create Private Prompt
        private_prompt_name = "My Private Assistant"
        private_prompt = create_prompt(
            db, name=private_prompt_name, system_instruction="You are a helpful private assistant.",
            prompt_type=PromptType.PRIVATE, creator_user_id=user1.user_id
        )
        assert private_prompt is not None, "Private prompt creation failed"
        assert private_prompt.prompt_type == PromptType.PRIVATE
        assert private_prompt.creator_user_id == user1.user_id
        log.info(f"Test 2.1: Private prompt '{private_prompt.name}' created by user {user1.user_id}.")

        # 2.2 Create Group Role Payload Prompt
        group_role_prompt_name = "Friendly Group Helper"
        group_role_prompt = create_prompt(
            db, name=group_role_prompt_name, system_instruction="I'm here to help the group!",
            prompt_type=PromptType.GROUP_ROLE_PAYLOAD, creator_user_id=user1.user_id
        )
        assert group_role_prompt is not None, "Group role payload prompt creation failed"
        assert group_role_prompt.prompt_type == PromptType.GROUP_ROLE_PAYLOAD
        log.info(f"Test 2.2: Group role payload prompt '{group_role_prompt.name}' created.")

        # 2.3 Retrieve prompts by user and type
        user_private_prompts = get_prompts_by_user_and_type(db, user_id=user1.user_id, prompt_type=PromptType.PRIVATE)
        assert len(user_private_prompts) == 1
        assert user_private_prompts[0].name == private_prompt_name
        log.info(f"Test 2.3: Retrieved {len(user_private_prompts)} private prompts for user.")

        # 2.4 Update prompt instruction
        updated_instruction = "You are an extremely efficient private assistant."
        updated_prompt = update_prompt_instruction(db, prompt_id=private_prompt.id,
                                                   new_system_instruction=updated_instruction, user_id=user1.user_id)
        assert updated_prompt is not None, "Prompt update failed"
        assert updated_prompt.system_instruction == updated_instruction
        log.info(f"Test 2.4: Prompt '{updated_prompt.name}' instruction updated.")

        # 2.5 Delete prompt
        delete_success = delete_prompt(db, prompt_id=private_prompt.id, user_id=user1.user_id)
        assert delete_success, "Prompt deletion failed"
        deleted_prompt_check = get_prompt_by_id_and_user(db, prompt_id=private_prompt.id, user_id=user1.user_id)
        assert deleted_prompt_check is None, "Prompt not actually deleted"
        log.info(f"Test 2.5: Prompt ID {private_prompt.id} deleted successfully.")

        # 2.6 Test retrieval of system prompts
        # Assuming '莉莉丝 (私聊用)' is loaded from prompts.yml as a PRIVATE system prompt
        lilith_system_prompt_name = PROMPTS_CONFIG.get("lilith_concise_private", {}).get("name", "莉莉丝 (私聊用)")
        system_prompt_lilith = get_system_prompt_by_name(db, name=lilith_system_prompt_name)
        assert system_prompt_lilith is not None, f"System prompt '{lilith_system_prompt_name}' not found."
        assert system_prompt_lilith.is_system_default
        assert system_prompt_lilith.prompt_type == PromptType.PRIVATE  # Check based on your prompts.yml
        log.info(f"Test 2.6: System prompt '{system_prompt_lilith.name}' retrieved successfully.")

        # --- Test 3: GroupSetting CRUD ---
        log.info("--- Running GroupSetting CRUD tests ---")
        test_group_id = "group987"
        gs1 = create_or_update_group_setting(
            db, group_id=test_group_id, current_mode="shared",
            shared_mode_role_prompt_id=group_role_prompt.id,  # Use the group_role_payload type prompt
            random_reply_enabled=True
        )
        assert gs1 is not None, "GroupSetting creation failed"
        assert gs1.current_mode == "shared"
        assert gs1.shared_mode_role_prompt_id == group_role_prompt.id
        log.info(f"Test 3.1: GroupSetting for {test_group_id} created in shared mode.")

        # Test updating to an invalid prompt ID (should not update the prompt_id)
        create_or_update_group_setting(db, group_id=test_group_id,
                                       shared_mode_role_prompt_id=99999)  # Assuming 99999 is invalid
        gs1_retrieved = get_group_setting(db, test_group_id)
        assert gs1_retrieved.shared_mode_role_prompt_id == group_role_prompt.id, "GroupSetting should not update with invalid prompt ID"
        log.info(f"Test 3.2: GroupSetting shared_mode_role_prompt_id correctly not updated with invalid ID.")

        # Test updating mode
        gs_updated = create_or_update_group_setting(db, group_id=test_group_id, current_mode="individual")
        assert gs_updated.current_mode == "individual"
        log.info(f"Test 3.3: GroupSetting for {test_group_id} updated to individual mode.")

        # --- Test 4: ChatSessionState CRUD ---
        log.info("--- Running ChatSessionState CRUD tests ---")
        # Ensure we have a valid PRIVATE prompt for chat session
        default_private_prompt = system_prompt_lilith  # Use a system private prompt
        if not default_private_prompt:  # Fallback if lilith wasn't loaded
            default_private_prompt = create_prompt(db, name="Default Test Private",
                                                   system_instruction="Default private.",
                                                   prompt_type=PromptType.PRIVATE, is_system_default=True)
        assert default_private_prompt is not None and default_private_prompt.prompt_type == PromptType.PRIVATE

        # 4.1 Create new private chat session
        session_private_chat_id = user1.user_id  # For private chat, chat_id is user_id
        chat_session1 = create_new_chat_session(
            db, telegram_chat_id=session_private_chat_id, telegram_user_id=user1.user_id,
            active_prompt_id=default_private_prompt.id, current_base_model="gemini-test-model"
        )
        assert chat_session1 is not None, "ChatSessionState creation for private chat failed"
        assert chat_session1.active_prompt_id == default_private_prompt.id
        assert chat_session1.is_active
        log.info(f"Test 4.1: Private ChatSessionState created (ID: {chat_session1.id}).")

        # 4.2 Update history
        mock_history = [{"role": "user", "parts": [{"text": "Hello"}]}]
        updated_session1 = update_chat_history(db, session_id=chat_session1.id, new_gemini_chat_history=mock_history)
        assert updated_session1 is not None, "Chat history update failed"
        deserialized_hist = get_deserialized_chat_history(updated_session1)
        assert deserialized_hist == mock_history
        log.info(f"Test 4.2: Chat history updated and deserialized for session {chat_session1.id}.")

        # 4.3 Archive and create new (simulating prompt change)
        another_private_prompt = create_prompt(db, name="Another Private", system_instruction="Another one",
                                               prompt_type=PromptType.PRIVATE, creator_user_id=user1.user_id)
        assert another_private_prompt is not None

        chat_session2 = create_new_chat_session(
            db, telegram_chat_id=session_private_chat_id, telegram_user_id=user1.user_id,
            active_prompt_id=another_private_prompt.id, current_base_model="gemini-test-model-v2"
        )
        assert chat_session2 is not None, "Second ChatSessionState creation failed"
        assert chat_session2.is_active
        assert chat_session2.id != chat_session1.id

        archived_session1 = get_active_chat_session_state(db, telegram_chat_id=session_private_chat_id,
                                                          telegram_user_id=user1.user_id)  # Should get session2
        assert archived_session1 is not None and archived_session1.id == chat_session2.id

        # Explicitly check old session state
        db.refresh(chat_session1)  # Refresh stale state from memory
        assert not chat_session1.is_active, "Old session was not archived"
        log.info(
            f"Test 4.3: Old session archived (ID: {chat_session1.id}), new session created (ID: {chat_session2.id}).")

        # --- Test 5: GroupMessageCache CRUD ---
        log.info("--- Running GroupMessageCache CRUD tests ---")
        msg_cache_group_id = "group_msg_cache_test"
        # Create a group setting for this group_id if it doesn't exist for FK constraint
        get_or_create_user(db, user_id="user_msg_sender", username="msgsender")
        create_or_update_group_setting(db, group_id=msg_cache_group_id)

        msg1_ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)
        msg1 = add_message_to_cache(db, group_id=msg_cache_group_id, message_id="msg1", user_id="user_msg_sender",
                                    text="Hello group", timestamp=msg1_ts)
        assert msg1 is not None

        msg2_ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
        msg2 = add_message_to_cache(db, group_id=msg_cache_group_id, message_id="msg2", user_id="user_msg_sender",
                                    text="How are you?", timestamp=msg2_ts)
        assert msg2 is not None
        log.info(f"Test 5.1: Added 2 messages to cache for group {msg_cache_group_id}.")

        recent_msgs = get_recent_messages_from_cache(db, group_id=msg_cache_group_id, limit=5)
        assert len(recent_msgs) == 2
        assert recent_msgs[0].message_id == "msg2", "Messages not retrieved in correct order"
        log.info(f"Test 5.2: Retrieved {len(recent_msgs)} messages from cache in correct order.")

        log.info("All database tests completed successfully.")

    except AssertionError as e:
        log.error(f"Assertion Error during tests: {e}", exc_info=True)
    except Exception as e:
        log.error(f"An unexpected error occurred during tests: {e}", exc_info=True)
    finally:
        db.close()
        log.info("Database session closed.")


if __name__ == "__main__":
    # Ensure the data directory exists for SQLite
    # It should be relative to the project root as defined in bot/__init__.py's DATABASE_URL
    data_dir = os.path.join(BOT_PROJECT_ROOT, "data")
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir)
            log.info(f"Created data directory: {data_dir}")
        except OSError as e:
            log.error(f"Could not create data directory {data_dir}: {e}. SQLite DB creation might fail.")
            # Depending on the error, you might want to exit here.

    run_tests()