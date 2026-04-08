import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, ADMIN_IDS
from database import db
from handlers import user_router, admin_router, payment_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)


async def on_startup():
    """Actions on bot startup"""
    logger.info("Initializing database...")
    await db.init_db()
    logger.info("Database initialized successfully")
    
    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🤖 Bot started successfully!")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def on_shutdown():
    """Actions on bot shutdown"""
    logger.info("Bot is shutting down...")
    
    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "🛑 Bot stopped!")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def main():
    """Main bot function"""
    global bot
    
    # Initialize bot and dispatcher
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )
    
    dp = Dispatcher()
    
    # Register routers
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(payment_router)
    
    # Startup actions
    await on_startup()
    
    try:
        # Start polling
        logger.info("Bot started successfully!")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        sys.exit(1)