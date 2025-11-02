from dotenv import load_dotenv
import os

# Load .env into environment (no-op if not present)
load_dotenv()

# Read tokens from environment, fallback to empty string
# Use uppercase variable names to be conventional in .env files
ChatGPT_TOKEN = os.getenv('CHATGPT_TOKEN', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
