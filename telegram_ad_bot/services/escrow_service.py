from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from telegram_ad_bot.models.user import User
from telegram_ad_bot.models.campaign import Campaign, CampaignStatus
from telegram_ad_bot.models.transaction import Transaction, TransactionType, TransactionStatus
from telegram_ad_bot.database.connection import create_db_session
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class EscrowServiceError(Exception):
    pass


class InsufficientFundsError(EscrowServiceError):
    pass


class InvalidTransactionError(EscrowServiceError):
    pass


class FundsAlreadyHeldError(EscrowServiceError):
    pass


class FundsNotHeldError(EscrowServiceError):
    pass


class EscrowService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        return await create_db_session()

    async def deposit_funds(self, user_id: int, amount: Decimal, description: Optional[str] = None) -> Transaction:
        if amount <= 0:
            raise InvalidTransactionError("Deposit amount must be positive")

        session = await self._get_session()
        try:
            user = await session.get(User, user_id)
            if not user:
                raise EscrowServiceError(f"User {user_id} not found")

            old_balance = user.balance
            user.balance += amount

            transaction = Transaction(
                user_id=user_id,
                transaction_type=TransactionType.DEPOSIT,
                amount=amount,
                status=TransactionStatus.COMPLETED,
                description=description or f"Deposit of {amount}",
                processed_at=datetime.utcnow()
            )
            
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            await session.refresh(user)
            
            logger.info(f"Deposited {amount} for user {user_id}: {old_balance} -> {user.balance}")
            return transaction
            
        except EscrowServiceError:
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error during deposit: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def hold_funds(self, campaign_id: int) -> Transaction:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise EscrowServiceError(f"Campaign {campaign_id} not found")

            advertiser = await session.get(User, campaign.advertiser_id)
            if not advertiser:
                raise EscrowServiceError(f"Advertiser {campaign.advertiser_id} not found")

            existing_hold = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.HOLD,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            if existing_hold.scalar_one_or_none():
                raise FundsAlreadyHeldError(f"Funds already held for campaign {campaign_id}")

            if advertiser.balance < campaign.price:
                raise InsufficientFundsError(
                    f"Insufficient funds: required={campaign.price}, available={advertiser.balance}"
                )

            old_balance = advertiser.balance
            advertiser.balance -= campaign.price

            transaction = Transaction(
                user_id=campaign.advertiser_id,
                campaign_id=campaign_id,
                transaction_type=TransactionType.HOLD,
                amount=-campaign.price,
                status=TransactionStatus.COMPLETED,
                description=f"Funds held for campaign {campaign_id}",
                processed_at=datetime.utcnow()
            )
            
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            await session.refresh(advertiser)
            
            logger.info(f"Held {campaign.price} for campaign {campaign_id}: {old_balance} -> {advertiser.balance}")
            return transaction
            
        except (EscrowServiceError, InsufficientFundsError, FundsAlreadyHeldError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error holding funds: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def release_funds(self, campaign_id: int, recipient_id: int) -> Transaction:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise EscrowServiceError(f"Campaign {campaign_id} not found")

            recipient = await session.get(User, recipient_id)
            if not recipient:
                raise EscrowServiceError(f"Recipient {recipient_id} not found")

            hold_transaction = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.HOLD,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            hold_tx = hold_transaction.scalar_one_or_none()
            if not hold_tx:
                raise FundsNotHeldError(f"No funds held for campaign {campaign_id}")

            existing_release = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.RELEASE,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            if existing_release.scalar_one_or_none():
                raise InvalidTransactionError(f"Funds already released for campaign {campaign_id}")

            old_balance = recipient.balance
            recipient.balance += campaign.price

            transaction = Transaction(
                user_id=recipient_id,
                campaign_id=campaign_id,
                transaction_type=TransactionType.RELEASE,
                amount=campaign.price,
                status=TransactionStatus.COMPLETED,
                description=f"Payment for campaign {campaign_id}",
                processed_at=datetime.utcnow()
            )
            
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            await session.refresh(recipient)
            
            logger.info(f"Released {campaign.price} to user {recipient_id} for campaign {campaign_id}: {old_balance} -> {recipient.balance}")
            return transaction
            
        except (EscrowServiceError, FundsNotHeldError, InvalidTransactionError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error releasing funds: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def refund_funds(self, campaign_id: int) -> Transaction:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise EscrowServiceError(f"Campaign {campaign_id} not found")

            advertiser = await session.get(User, campaign.advertiser_id)
            if not advertiser:
                raise EscrowServiceError(f"Advertiser {campaign.advertiser_id} not found")

            hold_transaction = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.HOLD,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            hold_tx = hold_transaction.scalar_one_or_none()
            if not hold_tx:
                raise FundsNotHeldError(f"No funds held for campaign {campaign_id}")

            existing_refund = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.REFUND,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            if existing_refund.scalar_one_or_none():
                raise InvalidTransactionError(f"Funds already refunded for campaign {campaign_id}")

            existing_release = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.RELEASE,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            if existing_release.scalar_one_or_none():
                raise InvalidTransactionError(f"Cannot refund: funds already released for campaign {campaign_id}")

            old_balance = advertiser.balance
            advertiser.balance += campaign.price

            transaction = Transaction(
                user_id=campaign.advertiser_id,
                campaign_id=campaign_id,
                transaction_type=TransactionType.REFUND,
                amount=campaign.price,
                status=TransactionStatus.COMPLETED,
                description=f"Refund for campaign {campaign_id}",
                processed_at=datetime.utcnow()
            )
            
            session.add(transaction)
            await session.commit()
            await session.refresh(transaction)
            await session.refresh(advertiser)
            
            logger.info(f"Refunded {campaign.price} to advertiser {campaign.advertiser_id} for campaign {campaign_id}: {old_balance} -> {advertiser.balance}")
            return transaction
            
        except (EscrowServiceError, FundsNotHeldError, InvalidTransactionError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error refunding funds: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_user_balance(self, user_id: int) -> Decimal:
        session = await self._get_session()
        try:
            user = await session.get(User, user_id)
            if not user:
                raise EscrowServiceError(f"User {user_id} not found")
            
            logger.debug(f"Retrieved balance for user {user_id}: {user.balance}")
            return user.balance
            
        except EscrowServiceError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user balance: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_held_amount(self, campaign_id: int) -> Optional[Decimal]:
        session = await self._get_session()
        try:
            hold_transaction = await session.execute(
                select(Transaction).where(
                    and_(
                        Transaction.campaign_id == campaign_id,
                        Transaction.transaction_type == TransactionType.HOLD,
                        Transaction.status == TransactionStatus.COMPLETED
                    )
                )
            )
            hold_tx = hold_transaction.scalar_one_or_none()
            
            if hold_tx:
                held_amount = abs(hold_tx.amount)
                logger.debug(f"Found held amount for campaign {campaign_id}: {held_amount}")
                return held_amount
            else:
                logger.debug(f"No held funds found for campaign {campaign_id}")
                return None
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting held amount: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_user_transactions(self, user_id: int, limit: Optional[int] = None) -> List[Transaction]:
        session = await self._get_session()
        try:
            stmt = select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.created_at.desc())
            
            if limit:
                stmt = stmt.limit(limit)
            
            result = await session.execute(stmt)
            transactions = result.scalars().all()
            
            logger.debug(f"Retrieved {len(transactions)} transactions for user {user_id}")
            return list(transactions)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user transactions: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_campaign_transactions(self, campaign_id: int) -> List[Transaction]:
        session = await self._get_session()
        try:
            stmt = select(Transaction).where(Transaction.campaign_id == campaign_id).order_by(Transaction.created_at.asc())
            
            result = await session.execute(stmt)
            transactions = result.scalars().all()
            
            logger.debug(f"Retrieved {len(transactions)} transactions for campaign {campaign_id}")
            return list(transactions)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting campaign transactions: {e}")
            raise EscrowServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()