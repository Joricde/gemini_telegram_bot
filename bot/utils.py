import logging
import os

# 创建日志目录
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志
logging.basicConfig(
    filename=os.path.join(log_dir, "bot.log"),
    format='%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s',
    encoding='utf-8'
)

# 获取 logger
logger = logging.getLogger("gemini_telegram_bot")
logger.setLevel(logging.INFO)

# 创建处理器
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s - %(lineno)d - %(message)s')
handler.setFormatter(formatter)

# 添加过滤器，仅打印项目中的日志
class MyFilter(logging.Filter):
    def filter(self, record):
        return record.name.startswith("gemini_telegram_bot")

# handler.addFilter(MyFilter())  # 根据需要使用或移除过滤器

# 将处理器添加到 logger
logger.addHandler(handler)