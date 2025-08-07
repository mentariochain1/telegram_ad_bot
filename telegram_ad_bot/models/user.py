"""User model for the Telegram Ad Bot."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from telegram_ad_bot.database.connection import Base

if TYPE_CHECKING:
    from telegram_ad_bot.models.channel import Channel
    from telegram_ad_bot.models.campaign import Campaign
    from telegram_ad_bot.models.transaction import Transaction


class UserRole(Enum):
    """User role enumeration."""
    ADVERTISER = "advertiser"
    CHANNEL_OWNER = "channel_owner"


class User(Base):
    """User model representing both advertisers and channel owners."""
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2), 
        default=Decimal('0.00'), 
        nullable=False
    )
    
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
    
    channels: Mapped[List["Channel"]] = relationship(
        "Channel", 
        back_populates="owner", 
        cascade="all, delete-orphan"
    )
    
    campaigns: Mapped[List["Campaign"]] = relationship(
        "Campaign", 
        back_populates="advertiser", 
        cascade="all, delete-orphan"
    )
    
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, role={self.role.value})>"
    
    @property
    def is_advertiser(self) -> bool:
        """Check if user is an advertiser."""
        return self.role == UserRole.ADVERTISER
    
    @property
    def is_channel_owner(self) -> bool:
        """Check if user is a channel owner."""
        return self.role == UserRole.CHANNEL_OWNER