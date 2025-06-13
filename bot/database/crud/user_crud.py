from sqlalchemy.orm import Session
from .. import models

def get_or_create_user(db: Session, telegram_user_id: int, first_name: str, last_name: str, username: str):
    """
    Retrieves an existing user or creates a new one if not found.
    """
    user = db.query(models.User).filter(models.User.telegram_user_id == telegram_user_id).first()
    if user:
        # Update user info if it has changed
        if user.first_name != first_name or user.last_name != last_name or user.username != username:
            user.first_name = first_name
            user.last_name = last_name
            user.username = username
            db.commit()
            db.refresh(user)
        return user
    else:
        new_user = models.User(
            telegram_user_id=telegram_user_id,
            first_name=first_name,
            last_name=last_name,
            username=username
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user