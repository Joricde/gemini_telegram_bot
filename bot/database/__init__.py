# bot/database/__init__.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from bot.core.config import settings
from bot.core.logging import logger # Import our logger

# Create the SQLAlchemy engine using the database URL from settings
engine = create_engine(
    settings.app.database.url,
    connect_args={"check_same_thread": False}, # Specific to SQLite
    echo=settings.app.database.echo
)

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    try:
        logger.info("Initializing database and creating tables...")
        # This is where SQLAlchemy creates the tables defined in models.py
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error during database initialization: {e}")
        # Depending on the desired behavior, you might want to exit the application
        # raise e
