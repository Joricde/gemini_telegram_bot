import logging
import os

# 创建日志目录
log_dir = "logs"  # 日志目录名称
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志
logging.basicConfig(
    filename=os.path.join(log_dir, "bot.log"),  # 日志文件路径
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,  # 将 WARNING 及以上级别日志输出到文件
)

# 获取 logger
logger = logging.getLogger("gemini_telegram_bot")  # 使用项目名称作为 logger 名称
logger.setLevel(logging.INFO)  # 设置 logger 级别为 INFO

# 创建处理器，仅处理 INFO 级别的日志
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# 添加过滤器，仅打印项目中的日志
class MyFilter(logging.Filter):
    def filter(self, record):
        return record.name.startswith("gemini_telegram_bot")  # 仅打印以项目名称开头的日志

handler.addFilter(MyFilter())

# 将处理器添加到 logger
logger.addHandler(handler)