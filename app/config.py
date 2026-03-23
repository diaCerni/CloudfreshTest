import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "global")
APP_ID = os.getenv("APP_ID", "")
PORT = int(os.getenv("PORT", "8000"))

if not PROJECT_ID:
    raise ValueError("Missing PROJECT_ID in .env")

if not APP_ID:
    raise ValueError("Missing APP_ID in .env")