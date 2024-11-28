import os

import google.generativeai as genai
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '../.env')

# 加载 .env 文件
load_dotenv(dotenv_path=dotenv_path)
# logger.info(dotenv_path)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content("Write a story about a magic backpack.", stream=True)
for chunk in response:
    print(chunk.text)
    print("_" * 80)
