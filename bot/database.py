import sqlite3

import yaml

# 加载配置文件
with open("config/config.yml", "r") as f:
    config = yaml.safe_load(f)

# 获取数据库配置
db_path = config.get("database", {}).get("path", "bot.db")

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 创建表格（如果不存在）
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        model_id TEXT
    )
    """
)
conn.commit()

def get_user(user_id):
    """
    获取用户信息。
    """
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

def add_user(user):
    """
    添加新用户。
    """
    cursor.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
        (user.id, user.username, user.first_name, user.last_name, None),
    )
    conn.commit()

def update_user_model(user_id, model_id):
    """
    更新用户模型。
    """
    cursor.execute(
        "UPDATE users SET model_id = ? WHERE id = ?", (model_id, user_id)
    )
    conn.commit()