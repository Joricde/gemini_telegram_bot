# In main.py
from bot.database import engine, init_db
from bot.database import models as db_models # Import all models to register them
from bot.utils import log
from bot import APP_CONFIG, PROMPTS_CONFIG  # Load initial prompts
from bot.database.crud import create_prompt, get_prompt_by_name
from bot.database import SessionLocal


def initialize_system_prompts():
    db = SessionLocal()
    try:
        log.info("Initializing system prompts...")
        default_gen_params = APP_CONFIG.get("gemini_settings", {}).get("default_generation_parameters", {})

        for key, prompt_data in PROMPTS_CONFIG.items():
            existing_prompt = get_prompt_by_name(db, name=prompt_data.get("name", key))
            if not existing_prompt:
                create_prompt(
                    db=db,
                    name=prompt_data.get("name", key), # Use key as fallback name
                    description=prompt_data.get("description"),
                    system_instruction=prompt_data.get("system_instruction", ""),
                    temperature=prompt_data.get("temperature", default_gen_params.get("temperature")),
                    top_p=prompt_data.get("top_p", default_gen_params.get("top_p")),
                    top_k=prompt_data.get("top_k", default_gen_params.get("top_k")),
                    max_output_tokens=prompt_data.get("max_output_tokens", default_gen_params.get("max_output_tokens")),
                    base_model_override=prompt_data.get("base_model_override"),
                    is_system_default=True # Mark prompts from yml as system defaults
                )
                log.info(f"Added system prompt: {prompt_data.get('name', key)}")
            # else:
            #     log.debug(f"System prompt '{prompt_data.get('name', key)}' already exists.")
    except Exception as e:
        log.error(f"Error initializing system prompts: {e}", exc_info=True)
    finally:
        db.close()


def main_app_setup():
    log.info("Application setup started.")
    # This ensures tables are created based on models in db_models
    # db_models.Base.metadata.create_all(bind=engine) # Alternative way to call it
    init_db() # This will call Base.metadata.create_all(bind=engine)
    log.info("Database initialized.")
    initialize_system_prompts() # Load prompts from YML into DB
    # ... rest of your bot setup and run logic ...

if __name__ == "__main__":
    main_app_setup()
    # ... application.run_polling() ...