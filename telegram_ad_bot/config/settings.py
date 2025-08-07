"""Configuration management for the Telegram Ad Bot."""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""
    
    def __init__(self):
        self.bot_token: str = self._get_required_env("BOT_TOKEN")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./telegram_ad_bot.db")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.log_file: Optional[str] = os.getenv("LOG_FILE")
        self.environment: str = os.getenv("ENVIRONMENT", "development")
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.default_campaign_duration_hours: int = int(os.getenv("DEFAULT_CAMPAIGN_DURATION_HOURS", "1"))
        
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"


settings = Settings()