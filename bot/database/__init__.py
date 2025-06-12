# gemini-telegram-bot/bot/database/__init__.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# 从 bot 包的 __init__.py 导入已加载的配置
from bot import DATABASE_URL, DATABASE_CONFIG # DATABASE_CONFIG 来自 app_config.yml
from bot.utils import log

# 创建数据库引擎
# connect_args 是 SQLite 特有的，用于允许多线程共享连接（Telegram bot 是异步的）
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=DATABASE_CONFIG.get("echo_sql", False), **engine_args)

# 创建 SessionLocal 类，用于创建数据库会话实例
# autocommit=False 和 autoflush=False 是推荐的默认设置，可以在需要时覆盖
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建 Base 类，我们的数据模型将继承这个类
Base = declarative_base()


def get_db():
    """
    数据库会话依赖项，用于在请求处理函数中获取数据库会话。
    确保会话在使用后正确关闭。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    初始化数据库，创建所有在 Base 中定义的表（如果它们尚不存在）。
    通常在应用启动时调用一次。
    """
    # 导入所有模型，确保它们在 Base.metadata 中注册
    # 最好在 models.py 中定义所有模型后，在这里导入它们
    from . import models # 这行会导致循环导入，应该在 models.py 定义后，在 main.py 或应用启动处调用
    Base.metadata.create_all(bind=engine)
    log.info("Database tables initialized.") # 可以用 log 替代

# 导出必要的对象，方便其他模块使用
# 例如: from bot.database import SessionLocal, engine, Base, init_db