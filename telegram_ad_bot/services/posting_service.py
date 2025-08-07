from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from aiogram import Bot

from telegram_ad_bot.models.campaign import Campaign, CampaignAssignment, CampaignStatus
from telegram_ad_bot.models.channel import Channel
from telegram_ad_bot.services.channel_service import ChannelService, BotPermissionError, PostingError, PinningError
from telegram_ad_bot.database.connection import create_db_session
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class PostingServiceError(Exception):
    pass


class CampaignNotFoundError(PostingServiceError):
    pass


class ChannelNotFoundError(PostingServiceError):
    pass


class AssignmentExistsError(PostingServiceError):
    pass


class PostingService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session
        self._owns_session = session is None
        self.channel_service = ChannelService(session)

    async def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        return await create_db_session()

    async def create_campaign_assignment(self, campaign_id: int, channel_id: int) -> CampaignAssignment:
        session = await self._get_session()
        try:
            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                raise CampaignNotFoundError(f"Campaign {campaign_id} not found")
            
            if not campaign.can_be_accepted:
                raise PostingServiceError(f"Campaign {campaign_id} cannot be accepted (status: {campaign.status})")
            
            channel = await session.get(Channel, channel_id)
            if not channel:
                raise ChannelNotFoundError(f"Channel {channel_id} not found")
            
            if not channel.is_ready_for_ads:
                raise PostingServiceError(f"Channel {channel_id} is not ready for ads")
            
            existing_assignment = campaign.assignment
            if existing_assignment:
                raise AssignmentExistsError(f"Campaign {campaign_id} already assigned to channel {existing_assignment.channel_id}")
            
            assignment = CampaignAssignment(
                campaign_id=campaign_id,
                channel_id=channel_id
            )
            
            session.add(assignment)
            
            campaign.status = CampaignStatus.ACTIVE
            
            await session.commit()
            await session.refresh(assignment)
            
            logger.info(f"Created assignment: campaign {campaign_id} -> channel {channel_id}")
            return assignment
            
        except (CampaignNotFoundError, ChannelNotFoundError, AssignmentExistsError, PostingServiceError):
            await session.rollback()
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error creating assignment: {e}")
            raise PostingServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def post_campaign_ad(self, bot: Bot, assignment_id: int, verification_service=None) -> Dict[str, Any]:
        session = await self._get_session()
        try:
            assignment = await session.get(CampaignAssignment, assignment_id)
            if not assignment:
                raise PostingServiceError(f"Assignment {assignment_id} not found")
            
            if assignment.is_posted:
                raise PostingServiceError(f"Assignment {assignment_id} already posted")
            
            await session.refresh(assignment, ['campaign', 'channel'])
            
            campaign = assignment.campaign
            channel = assignment.channel
            
            if not campaign or not channel:
                raise PostingServiceError(f"Missing campaign or channel data for assignment {assignment_id}")
            
            try:
                posting_result = await self.channel_service.post_and_pin_ad(
                    bot=bot,
                    channel_id=channel.telegram_channel_id,
                    ad_text=campaign.ad_text,
                    campaign_id=campaign.id
                )
                
                assignment.message_id = posting_result['message_id']
                assignment.posted_at = posting_result['posted_at']
                
                verification_time = datetime.utcnow() + timedelta(hours=campaign.duration_hours)
                assignment.verification_scheduled_at = verification_time
                
                await session.commit()
                await session.refresh(assignment)
                
                if verification_service:
                    try:
                        await verification_service.schedule_campaign_verification(
                            campaign.id, verification_time
                        )
                        logger.info(f"Scheduled verification for campaign {campaign.id} at {verification_time}")
                    except Exception as e:
                        logger.error(f"Failed to schedule verification for campaign {campaign.id}: {e}")
                
                result = {
                    'success': True,
                    'message_id': posting_result['message_id'],
                    'posted_at': posting_result['posted_at'],
                    'pinned': posting_result['pinned'],
                    'pin_error': posting_result.get('pin_error'),
                    'verification_scheduled_at': verification_time
                }
                
                logger.info(f"Successfully posted ad for assignment {assignment_id}: {result}")
                return result
                
            except (BotPermissionError, PostingError, PinningError) as e:
                campaign.status = CampaignStatus.FAILED
                await session.commit()
                
                logger.error(f"Failed to post ad for assignment {assignment_id}: {e}")
                raise PostingServiceError(f"Posting failed: {e}")
            
        except PostingServiceError:
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error posting ad: {e}")
            raise PostingServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def verify_campaign_compliance(self, bot: Bot, assignment_id: int) -> Dict[str, Any]:
        session = await self._get_session()
        try:
            assignment = await session.get(CampaignAssignment, assignment_id)
            if not assignment:
                raise PostingServiceError(f"Assignment {assignment_id} not found")
            
            if not assignment.is_posted:
                raise PostingServiceError(f"Assignment {assignment_id} not posted yet")
            
            if assignment.is_verified:
                logger.debug(f"Assignment {assignment_id} already verified")
                return {
                    'assignment_id': assignment_id,
                    'is_compliant': assignment.is_compliant,
                    'already_verified': True
                }
            
            await session.refresh(assignment, ['channel'])
            channel = assignment.channel
            
            try:
                is_pinned = await self.channel_service.verify_message_pinned(
                    bot=bot,
                    channel_id=channel.telegram_channel_id,
                    message_id=assignment.message_id
                )
                
                assignment.is_compliant = is_pinned
                await session.commit()
                
                result = {
                    'assignment_id': assignment_id,
                    'is_compliant': is_pinned,
                    'verified_at': datetime.utcnow(),
                    'already_verified': False
                }
                
                logger.info(f"Verified compliance for assignment {assignment_id}: compliant={is_pinned}")
                return result
                
            except BotPermissionError as e:
                logger.error(f"Cannot verify compliance for assignment {assignment_id}: {e}")
                assignment.is_compliant = False
                await session.commit()
                
                return {
                    'assignment_id': assignment_id,
                    'is_compliant': False,
                    'error': str(e),
                    'verified_at': datetime.utcnow(),
                    'already_verified': False
                }
            
        except PostingServiceError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error verifying compliance: {e}")
            raise PostingServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_assignment_by_id(self, assignment_id: int) -> Optional[CampaignAssignment]:
        session = await self._get_session()
        try:
            assignment = await session.get(CampaignAssignment, assignment_id)
            return assignment
        except SQLAlchemyError as e:
            logger.error(f"Database error getting assignment {assignment_id}: {e}")
            raise PostingServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_assignments_for_verification(self) -> list[CampaignAssignment]:
        session = await self._get_session()
        try:
            now = datetime.utcnow()
            stmt = select(CampaignAssignment).where(
                CampaignAssignment.verification_scheduled_at <= now,
                CampaignAssignment.is_compliant.is_(None),
                CampaignAssignment.message_id.is_not(None)
            )
            result = await session.execute(stmt)
            assignments = result.scalars().all()
            
            logger.debug(f"Found {len(assignments)} assignments ready for verification")
            return list(assignments)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting assignments for verification: {e}")
            raise PostingServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_assignment_status(self, assignment_id: int) -> Dict[str, Any]:
        session = await self._get_session()
        try:
            assignment = await session.get(CampaignAssignment, assignment_id)
            if not assignment:
                raise PostingServiceError(f"Assignment {assignment_id} not found")
            
            await session.refresh(assignment, ['campaign', 'channel'])
            
            status = {
                'assignment_id': assignment_id,
                'campaign_id': assignment.campaign_id,
                'channel_id': assignment.channel_id,
                'channel_name': assignment.channel.channel_name if assignment.channel else None,
                'is_posted': assignment.is_posted,
                'message_id': assignment.message_id,
                'posted_at': assignment.posted_at,
                'verification_scheduled_at': assignment.verification_scheduled_at,
                'is_verified': assignment.is_verified,
                'is_compliant': assignment.is_compliant,
                'settlement_processed': assignment.settlement_processed,
                'campaign_status': assignment.campaign.status.value if assignment.campaign else None
            }
            
            return status
            
        except PostingServiceError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error getting assignment status: {e}")
            raise PostingServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()