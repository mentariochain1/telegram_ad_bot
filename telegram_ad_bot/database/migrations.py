"""Database migration utilities for the Telegram Ad Bot."""

import asyncio
from typing import Optional

from telegram_ad_bot.config.logging import get_logger
from telegram_ad_bot.database.connection import init_database, drop_database, engine

logger = get_logger(__name__)


async def migrate_database(drop_existing: bool = False):
    """
    Run database migrations.
    
    Args:
        drop_existing: If True, drop all existing tables before creating new ones
    """
    try:
        if drop_existing:
            logger.warning("Dropping existing database tables...")
            await drop_database()
        
        logger.info("Running database migrations...")
        await init_database()
        logger.info("Database migrations completed successfully")
        
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        raise


async def check_database_connection():
    """Check if database connection is working."""
    try:
        from sqlalchemy import text
        
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.fetchone()
        
        logger.info("Database connection successful")
        return True
        
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


async def reset_database():
    """Reset database by dropping and recreating all tables."""
    logger.warning("Resetting database - all data will be lost!")
    await migrate_database(drop_existing=True)


if __name__ == "__main__":
    import sys
    
    async def main():
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()
            
            if command == "migrate":
                await migrate_database()
            elif command == "reset":
                await reset_database()
            elif command == "check":
                success = await check_database_connection()
                sys.exit(0 if success else 1)
            else:
                print("Usage: python -m telegram_ad_bot.database.migrations [migrate|reset|check]")
                sys.exit(1)
        else:
            await migrate_database()
    
    asyncio.run(main())