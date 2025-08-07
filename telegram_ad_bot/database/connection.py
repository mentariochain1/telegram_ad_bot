"""Database connection management."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from telegram_ad_bot.config.settings import settings
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db_session():
    """Get database session generator for dependency injection."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_db_session() -> AsyncSession:
    """Create a new database session."""
    return AsyncSessionLocal()


async def init_database():
    """Initialize database tables."""
    logger.info("Initializing database...")
    async with engine.begin() as conn:
        from telegram_ad_bot.models import (
            User, Channel, Campaign, CampaignAssignment, Transaction
        )
        
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database initialization complete")


async def drop_database():
    """Drop all database tables (for testing/development)."""
    logger.warning("Dropping all database tables...")
    async with engine.begin() as conn:
        from telegram_ad_bot.models import (
            User, Channel, Campaign, CampaignAssignment, Transaction
        )
        
        await conn.run_sync(Base.metadata.drop_all)
    
    logger.warning("All database tables dropped")