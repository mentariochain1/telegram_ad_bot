"""Transaction model for the Telegram Ad Bot."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from telegram_ad_bot.database.connection import Base

if TYPE_CHECKING:
    from telegram_ad_bot.models.user import User
    from telegram_ad_bot.models.campaign import Campaign


class TransactionType(Enum):
    """Transaction type enumeration."""
    DEPOSIT = "deposit"
    HOLD = "hold"
    RELEASE = "release"
    REFUND = "refund"


class TransactionStatus(Enum):
    """Transaction status enumeration."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Transaction(Base):
    """Transaction model for escrow operations and audit trail."""
    
    __tablename__ = "transactions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Campaign can be null for general deposits/withdrawals
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    
    transaction_type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType), 
        nullable=False,
        index=True
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2), 
        nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus), 
        default=TransactionStatus.PENDING, 
        nullable=False,
        index=True
    )
    
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
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
    
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    campaign: Mapped[Optional["Campaign"]] = relationship("Campaign", back_populates="transactions")
    
    def __repr__(self) -> str:
        """String representation of Transaction."""
        return f"<Transaction(id={self.id}, type={self.transaction_type.value}, amount={self.amount}, status={self.status.value})>"
    
    @property
    def is_completed(self) -> bool:
        """Check if transaction is completed."""
        return self.status == TransactionStatus.COMPLETED
    
    @property
    def is_pending(self) -> bool:
        """Check if transaction is pending."""
        return self.status == TransactionStatus.PENDING
    
    @property
    def is_failed(self) -> bool:
        """Check if transaction failed."""
        return self.status == TransactionStatus.FAILED
    
    def mark_completed(self) -> None:
        """Mark transaction as completed."""
        self.status = TransactionStatus.COMPLETED
        self.processed_at = func.now()
    
    def mark_failed(self, description: Optional[str] = None) -> None:
        """Mark transaction as failed."""
        self.status = TransactionStatus.FAILED
        self.processed_at = func.now()
        if description:
            self.description = description