from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from telegram_ad_bot.models.user import User, UserRole
from telegram_ad_bot.models.transaction import Transaction, TransactionType, TransactionStatus
from telegram_ad_bot.database.connection import create_db_session
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class UserServiceError(Exception):
    pass


class UserNotFoundError(UserServiceError):
    pass


class InsufficientFundsError(UserServiceError):
    pass


class UserService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        return await create_db_session()

    async def register_user(self, telegram_id: int, username: Optional[str], role: UserRole) -> User:
        session = await self._get_session()
        try:
            existing_user = await self.get_user_by_telegram_id(telegram_id)
            if existing_user:
                logger.info(f"User {telegram_id} already exists, returning existing user")
                return existing_user

            user = User(
                telegram_id=telegram_id,
                username=username,
                role=role,
                balance=Decimal('0.00'),
                is_active=True
            )
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"Registered new user: {telegram_id} as {role.value}")
            return user
            
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Failed to register user {telegram_id}: {e}")
            raise UserServiceError(f"User registration failed: {e}")
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error during user registration: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        session = await self._get_session()
        try:
            stmt = select(User).where(User.telegram_id == telegram_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user:
                logger.debug(f"Found user: {telegram_id}")
            else:
                logger.debug(f"User not found: {telegram_id}")
            
            return user
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user {telegram_id}: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        session = await self._get_session()
        try:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user:
                logger.debug(f"Found user by ID: {user_id}")
            else:
                logger.debug(f"User not found by ID: {user_id}")
            
            return user
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user by ID {user_id}: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def update_user_balance(self, user_id: int, amount: Decimal, transaction_type: TransactionType, 
                                campaign_id: Optional[int] = None, description: Optional[str] = None) -> User:
        session = await self._get_session()
        try:
            user = await session.get(User, user_id)
            if not user:
                raise UserNotFoundError(f"User {user_id} not found")

            old_balance = user.balance
            new_balance = old_balance + amount

            if new_balance < 0:
                raise InsufficientFundsError(f"Insufficient funds: current={old_balance}, requested={amount}")

            user.balance = new_balance

            transaction = Transaction(
                user_id=user_id,
                campaign_id=campaign_id,
                transaction_type=transaction_type,
                amount=amount,
                status=TransactionStatus.COMPLETED,
                description=description,
                processed_at=datetime.utcnow()
            )
            
            session.add(transaction)
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"Updated user {user_id} balance: {old_balance} -> {new_balance} (change: {amount})")
            return user
            
        except (UserNotFoundError, InsufficientFundsError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error updating user balance: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_user_balance(self, user_id: int) -> Decimal:
        session = await self._get_session()
        try:
            user = await session.get(User, user_id)
            if not user:
                raise UserNotFoundError(f"User {user_id} not found")
            
            logger.debug(f"Retrieved balance for user {user_id}: {user.balance}")
            return user.balance
            
        except UserNotFoundError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error getting user balance: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def deactivate_user(self, user_id: int) -> bool:
        session = await self._get_session()
        try:
            stmt = update(User).where(User.id == user_id).values(is_active=False)
            result = await session.execute(stmt)
            await session.commit()
            
            success = result.rowcount > 0
            if success:
                logger.info(f"Deactivated user {user_id}")
            else:
                logger.warning(f"User {user_id} not found for deactivation")
            
            return success
            
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error deactivating user: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_active_users_by_role(self, role: UserRole) -> List[User]:
        session = await self._get_session()
        try:
            stmt = select(User).where(User.role == role, User.is_active == True)
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            logger.debug(f"Found {len(users)} active users with role {role.value}")
            return list(users)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting users by role: {e}")
            raise UserServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()