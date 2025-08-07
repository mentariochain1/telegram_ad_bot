"""Campaign and CampaignAssignment models for the Telegram Ad Bot."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SQLEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from telegram_ad_bot.database.connection import Base

if TYPE_CHECKING:
    from telegram_ad_bot.models.user import User
    from telegram_ad_bot.models.channel import Channel
    from telegram_ad_bot.models.transaction import Transaction


class CampaignStatus(Enum):
    """Campaign status enumeration."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Campaign(Base):
    """Campaign model representing advertising campaigns."""
    
    __tablename__ = "campaigns"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ad_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    price: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2), 
        nullable=False
    )
    duration_hours: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    status: Mapped[CampaignStatus] = mapped_column(
        SQLEnum(CampaignStatus), 
        default=CampaignStatus.PENDING, 
        nullable=False,
        index=True
    )
    
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
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
    
    advertiser: Mapped["User"] = relationship("User", back_populates="campaigns")
    
    # One-to-one relationship: each campaign can only be assigned to one channel
    assignment: Mapped[Optional["CampaignAssignment"]] = relationship(
        "CampaignAssignment", 
        back_populates="campaign", 
        uselist=False,
        cascade="all, delete-orphan"
    )
    
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", 
        back_populates="campaign", 
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        """String representation of Campaign."""
        return f"<Campaign(id={self.id}, status={self.status.value}, price={self.price})>"
    
    @property
    def is_active(self) -> bool:
        """Check if campaign is currently active."""
        return self.status == CampaignStatus.ACTIVE
    
    @property
    def is_completed(self) -> bool:
        """Check if campaign is completed."""
        return self.status == CampaignStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Check if campaign failed."""
        return self.status == CampaignStatus.FAILED
    
    @property
    def can_be_accepted(self) -> bool:
        """Check if campaign can be accepted by channel owners."""
        return self.status == CampaignStatus.PENDING


class CampaignAssignment(Base):
    """Campaign assignment model linking campaigns to channels."""
    
    __tablename__ = "campaign_assignments"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    
    # Telegram message ID for tracking posted ads
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Compliance verification: None=pending, True=compliant, False=non-compliant
    is_compliant: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    settlement_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
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
    
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="assignment")
    channel: Mapped["Channel"] = relationship("Channel", back_populates="campaign_assignments")
    
    def __repr__(self) -> str:
        """String representation of CampaignAssignment."""
        return f"<CampaignAssignment(id={self.id}, campaign_id={self.campaign_id}, channel_id={self.channel_id})>"
    
    @property
    def is_posted(self) -> bool:
        """Check if the ad has been posted."""
        return self.message_id is not None and self.posted_at is not None
    
    @property
    def is_verified(self) -> bool:
        """Check if compliance verification has been completed."""
        return self.is_compliant is not None
    
    @property
    def is_settlement_ready(self) -> bool:
        """Check if assignment is ready for settlement."""
        return self.is_verified and not self.settlement_processed