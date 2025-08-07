"""Channel model for the Telegram Ad Bot."""

from datetime import datetime
from typing import List, TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from telegram_ad_bot.database.connection import Base

if TYPE_CHECKING:
    from telegram_ad_bot.models.user import User
    from telegram_ad_bot.models.campaign import CampaignAssignment


class Channel(Base):
    """Channel model representing Telegram channels available for advertising."""
    
    __tablename__ = "channels"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_channel_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Channel must be verified and bot must have admin status to accept ads
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_admin_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )
    
    owner: Mapped["User"] = relationship("User", back_populates="channels")
    
    campaign_assignments: Mapped[List["CampaignAssignment"]] = relationship(
        "CampaignAssignment", 
        back_populates="channel", 
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        """String representation of Channel."""
        return f"<Channel(id={self.id}, name={self.channel_name}, telegram_id={self.telegram_channel_id})>"
    
    @property
    def is_ready_for_ads(self) -> bool:
        """Check if channel is ready to accept advertisements."""
        return self.is_verified and self.bot_admin_status
    
    @property
    def display_name(self) -> str:
        """Get display name for the channel."""
        return self.channel_name or f"Channel {self.telegram_channel_id}"