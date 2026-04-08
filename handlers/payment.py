from aiogram import Router
from config import UPI_ID
import logging

logger = logging.getLogger(__name__)
payment_router = Router()

# Payment logic is handled in user.py
# This file can be extended for additional payment features