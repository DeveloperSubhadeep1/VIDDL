import os

API_ID = int(os.environ.get("API_ID", "27972068"))
API_HASH = os.environ.get("API_HASH", "6e7e2f5cdddba536b8e603b3155223c1")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8335925557:AAHKNKJMhL990oUrbCQBUXUucTNkVqjJjtc")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://viddl:viddl@cluster0.lnh9rzf.mongodb.net/?appName=Cluster0")
DOWNLOAD_DIR  = "./downloads"
COOKIES_FILE  = os.environ.get("COOKIES_FILE", "./cookies.txt")  # export from browser using cookies.txt extension
# DB_NAME = "cluster0"
# # Ensure download directory exists
# os.makedirs(DOWNLOAD_DIR, exist_ok=True)


DB_NAME      = os.environ.get("DB_NAME", "leechbot")
 
MAX_QUEUE_SIZE   = int(os.environ.get("MAX_QUEUE_SIZE", "200"))
MAX_BATCH_URLS   = int(os.environ.get("MAX_BATCH_URLS", "500"))
MAX_FILE_SIZE_GB = float(os.environ.get("MAX_FILE_SIZE_GB", "2.0"))
MAX_RETRIES      = int(os.environ.get("MAX_RETRIES", "3"))
 
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
 
