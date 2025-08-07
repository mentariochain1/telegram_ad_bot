"""Main entry point for the Telegram Ad Bot."""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from telegram_ad_bot.config.logging import setup_logging
from telegram_ad_bot.config.settings import settings
from telegram_ad_bot.database.migrations import init_database
from telegram_ad_bot.handlers.bot_handlers import router
from telegram_ad_bot.services.verification_service import VerificationService

verification_service = None

def get_verification_service():
    """Get the global verification service instance."""
    return verification_service


async def main():
    """Main application entry point."""
    global verification_service
    
    setup_logging(settings.log_file)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Telegram Ad Bot...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {settings.debug}")
    
    try:
        await init_database()
        logger.info("Database initialized successfully")
        
        bot = Bot(token=settings.bot_token)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)
        
        verification_service = VerificationService(bot)
        await verification_service.start_scheduler()
        logger.info("Verification service started")
        
        dp.include_router(router)
        
        logger.info("Bot handlers registered")
        
        try:
            await dp.start_polling(bot)
        finally:
            if verification_service:
                await verification_service.stop_scheduler()
                logger.info("Verification service stopped")
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        if verification_service:
            await verification_service.stop_scheduler()
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Bot crashed: {e}", exc_info=True)