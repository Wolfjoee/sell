import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]

# Database
DATABASE_PATH = os.getenv('DATABASE_PATH', 'bot_database.db')

# Payment Configuration
UPI_ID = os.getenv('UPI_ID', 'merchant@upi')
UPI_NAME = os.getenv('UPI_NAME', 'Merchant')  # Name shown in UPI apps

# Thresholds
LOW_STOCK_THRESHOLD = int(os.getenv('LOW_STOCK_THRESHOLD', '5'))
LOW_CODE_THRESHOLD = int(os.getenv('LOW_CODE_THRESHOLD', '10'))

# Validation
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required in environment variables")

if not ADMIN_IDS:
    raise ValueError("At least one ADMIN_ID is required")