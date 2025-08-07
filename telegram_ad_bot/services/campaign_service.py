from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from telegram_ad_bot.models.campaign import Campaign, CampaignStatus, CampaignAssignment
from telegram_ad_bot.models.user import User, UserRole
from telegram_ad_bot.models.channel import Channel
from telegram_ad_bot.database.connection import create_db_session
from telegram_ad_bot.config.settings import settings
from telegram_ad_bot.config.logging import get_logger
from telegram_ad_bot.services.escrow_service import EscrowService, InsufficientFundsError

logger = get_logger(__name__)


class CampaignServiceError(Exception):
    pass


class CampaignNotFoundError(CampaignServiceError):
    pass


class InvalidAdvertiserError(CampaignServiceError):
    pass


class CampaignValidationError(CampaignServiceError):
    pass


class CampaignAlreadyAssignedError(CampaignServiceError):
    pass


class InsufficientBalanceError(CampaignServiceError):
    pass


class CampaignService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        return await create_db_session()

    def _validate_ad_content(self, ad_text: str) -> None:
        if not ad_text or len(ad_text.strip()) == 0:
            raise CampaignValidationError("Ad text cannot be empty")
            
        if len(ad_text.strip()) < 10:
            raise CampaignValidationError("Ad text must be at least 10 characters long")
            
        if len(ad_text.strip()) > 1000:
            raise CampaignValidationError("Ad text cannot exceed 1000 characters")
        
        forbidden_words = [
            'scam', 'fraud', 'hack', 'illegal', 'drugs', 'weapons', 'violence',
            'hate', 'discrimination', 'adult', 'porn', 'gambling', 'casino'
        ]
        
        ad_text_lower = ad_text.lower()
        for word in forbidden_words:
            if word in ad_text_lower:
                raise CampaignValidationError(f"Ad content contains prohibited word: '{word}'")
        
        if ad_text.count('http') > 2:
            raise CampaignValidationError("Ad text cannot contain more than 2 links")

    async def create_campaign(self, advertiser_id: int, ad_text: str, price: Decimal, 
                            duration_hours: Optional[int] = None) -> Campaign:
        session = await self._get_session()
        try:
            advertiser = await session.get(User, advertiser_id)
            if not advertiser:
                raise InvalidAdvertiserError(f"Advertiser {advertiser_id} not found")
            
            if not advertiser.is_advertiser:
                raise InvalidAdvertiserError(f"User {advertiser_id} is not an advertiser")

            self._validate_ad_content(ad_text.strip())

            if price <= 0:
                raise CampaignValidationError("Campaign price must be positive")

            if price > Decimal('10000'):
                raise CampaignValidationError("Campaign price cannot exceed $10,000")

            if advertiser.balance < price:
                raise InsufficientBalanceError(f"Insufficient balance: required ${price}, available ${advertiser.balance}")

            if duration_hours is None:
                duration_hours = settings.default_campaign_duration_hours

            if duration_hours <= 0:
                raise CampaignValidationError("Campaign duration must be positive")

            expires_at = datetime.utcnow() + timedelta(days=7)

            campaign = Campaign(
                advertiser_id=advertiser_id,
                ad_text=ad_text.strip(),
                price=price,
                duration_hours=duration_hours,
                status=CampaignStatus.PENDING,
                expires_at=expires_at
            )
            
            session.add(campaign)
            await session.commit()
            await session.refresh(campaign)
            
            logger.info(f"Created campaign {campaign.id} for advertiser {advertiser_id} with price {price}")
            return campaign
            
        except (InvalidAdvertiserError, CampaignValidationError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error creating campaign: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_campaign_by_id(self, campaign_id: int) -> Optional[Campaign]:
        session = await self._get_session()
        try:
            stmt = select(Campaign).options(
                selectinload(Campaign.advertiser),
                selectinload(Campaign.assignment)
            ).where(Campaign.id == campaign_id)
            result = await session.execute(stmt)
            campaign = result.scalar_one_or_none()
            
            if campaign:
                logger.debug(f"Found campaign: {campaign_id}")
            else:
                logger.debug(f"Campaign not found: {campaign_id}")
            
            return campaign
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting campaign {campaign_id}: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_available_campaigns(self, channel_id: Optional[int] = None) -> List[Campaign]:
        session = await self._get_session()
        try:
            stmt = select(Campaign).options(
                selectinload(Campaign.advertiser)
            ).where(
                Campaign.status == CampaignStatus.PENDING,
                Campaign.expires_at > datetime.utcnow()
            ).order_by(Campaign.created_at.desc())
            
            result = await session.execute(stmt)
            campaigns = result.scalars().all()
            
            available_campaigns = []
            for campaign in campaigns:
                if not hasattr(campaign, 'assignment') or campaign.assignment is None:
                    available_campaigns.append(campaign)
            
            logger.debug(f"Found {len(available_campaigns)} available campaigns")
            return available_campaigns
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting available campaigns: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_campaigns_by_advertiser(self, advertiser_id: int) -> List[Campaign]:
        session = await self._get_session()
        try:
            stmt = select(Campaign).options(
                selectinload(Campaign.assignment)
            ).where(Campaign.advertiser_id == advertiser_id).order_by(Campaign.created_at.desc())
            
            result = await session.execute(stmt)
            campaigns = result.scalars().all()
            
            logger.debug(f"Found {len(campaigns)} campaigns for advertiser {advertiser_id}")
            return list(campaigns)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting campaigns for advertiser {advertiser_id}: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def accept_campaign(self, campaign_id: int, channel_id: int) -> CampaignAssignment:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise CampaignNotFoundError(f"Campaign {campaign_id} not found")

            if not campaign.can_be_accepted:
                raise CampaignValidationError(f"Campaign {campaign_id} cannot be accepted (status: {campaign.status.value})")

            channel = await session.get(Channel, channel_id)
            if not channel:
                raise CampaignServiceError(f"Channel {channel_id} not found")

            if not channel.is_ready_for_ads:
                raise CampaignValidationError(f"Channel {channel_id} is not ready for ads")

            existing_assignment = await session.execute(
                select(CampaignAssignment).where(CampaignAssignment.campaign_id == campaign_id)
            )
            if existing_assignment.scalar_one_or_none():
                raise CampaignAlreadyAssignedError(f"Campaign {campaign_id} is already assigned")

            escrow_service = EscrowService(session)
            try:
                await escrow_service.hold_funds(campaign_id)
            except InsufficientFundsError as e:
                raise CampaignValidationError(f"Cannot accept campaign: {str(e)}")

            campaign.status = CampaignStatus.ACTIVE

            assignment = CampaignAssignment(
                campaign_id=campaign_id,
                channel_id=channel_id
            )
            
            session.add(assignment)
            await session.commit()
            await session.refresh(assignment)
            await session.refresh(campaign)
            
            logger.info(f"Campaign {campaign_id} accepted by channel {channel_id}, funds held in escrow")
            return assignment
            
        except (CampaignNotFoundError, CampaignValidationError, CampaignAlreadyAssignedError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error accepting campaign: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def update_campaign_status(self, campaign_id: int, status: CampaignStatus, 
                                   notification_bot=None) -> Campaign:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise CampaignNotFoundError(f"Campaign {campaign_id} not found")

            old_status = campaign.status
            campaign.status = status
            await session.commit()
            await session.refresh(campaign)
            
            if notification_bot and old_status != status:
                from telegram_ad_bot.services.notification_service import NotificationService
                notification_service = NotificationService(notification_bot)
                
                if status == CampaignStatus.COMPLETED and campaign.assignment:
                    await notification_service.notify_campaign_completed(
                        campaign, campaign.assignment.channel, float(campaign.price)
                    )
                elif status == CampaignStatus.FAILED and campaign.assignment:
                    await notification_service.notify_campaign_failed(
                        campaign, campaign.assignment.channel, "Campaign monitoring detected non-compliance"
                    )
            
            logger.info(f"Campaign {campaign_id} status updated: {old_status.value} -> {status.value}")
            return campaign
            
        except CampaignNotFoundError:
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error updating campaign status: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def cancel_campaign(self, campaign_id: int, advertiser_id: int) -> Campaign:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise CampaignNotFoundError(f"Campaign {campaign_id} not found")

            if campaign.advertiser_id != advertiser_id:
                raise CampaignValidationError(f"Campaign {campaign_id} does not belong to advertiser {advertiser_id}")

            if campaign.status not in [CampaignStatus.PENDING, CampaignStatus.ACTIVE]:
                raise CampaignValidationError(f"Campaign {campaign_id} cannot be cancelled (status: {campaign.status.value})")

            campaign.status = CampaignStatus.CANCELLED
            await session.commit()
            await session.refresh(campaign)
            
            logger.info(f"Campaign {campaign_id} cancelled by advertiser {advertiser_id}")
            return campaign
            
        except (CampaignNotFoundError, CampaignValidationError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error cancelling campaign: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_active_campaigns(self) -> List[Campaign]:
        session = await self._get_session()
        try:
            stmt = select(Campaign).options(
                selectinload(Campaign.assignment).selectinload(CampaignAssignment.channel)
            ).where(Campaign.status == CampaignStatus.ACTIVE)
            
            result = await session.execute(stmt)
            campaigns = result.scalars().all()
            
            logger.debug(f"Found {len(campaigns)} active campaigns")
            return list(campaigns)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting active campaigns: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_expired_campaigns(self) -> List[Campaign]:
        session = await self._get_session()
        try:
            stmt = select(Campaign).where(
                Campaign.status == CampaignStatus.PENDING,
                Campaign.expires_at <= datetime.utcnow()
            )
            
            result = await session.execute(stmt)
            campaigns = result.scalars().all()
            
            logger.debug(f"Found {len(campaigns)} expired campaigns")
            return list(campaigns)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting expired campaigns: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_campaigns_for_monitoring(self) -> List[Campaign]:
        """Get campaigns that need monitoring for compliance."""
        session = await self._get_session()
        try:
            stmt = select(Campaign).options(
                selectinload(Campaign.assignment).selectinload(CampaignAssignment.channel)
            ).where(
                Campaign.status == CampaignStatus.ACTIVE
            )
            
            result = await session.execute(stmt)
            campaigns = result.scalars().all()
            
            monitoring_campaigns = []
            for campaign in campaigns:
                if (campaign.assignment and 
                    campaign.assignment.is_posted and 
                    not campaign.assignment.is_verified):
                    monitoring_campaigns.append(campaign)
            
            logger.debug(f"Found {len(monitoring_campaigns)} campaigns needing monitoring")
            return monitoring_campaigns
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting campaigns for monitoring: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def mark_campaign_posted(self, campaign_id: int, message_id: int) -> CampaignAssignment:
        """Mark a campaign as posted with the message ID."""
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise CampaignNotFoundError(f"Campaign {campaign_id} not found")

            if not campaign.assignment:
                raise CampaignServiceError(f"Campaign {campaign_id} has no assignment")

            assignment = campaign.assignment
            assignment.message_id = message_id
            assignment.posted_at = datetime.utcnow()
            
            await session.commit()
            await session.refresh(assignment)
            
            logger.info(f"Campaign {campaign_id} marked as posted with message ID {message_id}")
            return assignment
            
        except (CampaignNotFoundError, CampaignServiceError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error marking campaign as posted: {e}")
            raise CampaignServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()