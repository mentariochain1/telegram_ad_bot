from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, update
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from telegram_ad_bot.models.campaign import Campaign, CampaignStatus, CampaignAssignment
from telegram_ad_bot.services.campaign_service import CampaignService
from telegram_ad_bot.services.posting_service import PostingService
from telegram_ad_bot.services.escrow_service import EscrowService
from telegram_ad_bot.database.connection import create_db_session
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class VerificationServiceError(Exception):
    pass


class VerificationService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = None
        self.campaign_service = CampaignService()
        self.posting_service = PostingService()
        self.escrow_service = EscrowService()
        self._setup_scheduler()

    def _setup_scheduler(self):
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': AsyncIOExecutor()
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': 3,
            'misfire_grace_time': 30
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        logger.info("Verification scheduler initialized")

    async def start_scheduler(self):
        if not self.scheduler.running:
            self.scheduler.start()
            
            self.scheduler.add_job(
                self._periodic_verification_check,
                IntervalTrigger(minutes=5),
                id='periodic_verification_check',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                self._cleanup_expired_campaigns,
                IntervalTrigger(hours=1),
                id='cleanup_expired_campaigns',
                replace_existing=True
            )
            
            logger.info("Verification scheduler started with periodic jobs")

    async def stop_scheduler(self):
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Verification scheduler stopped")

    async def schedule_campaign_verification(self, campaign_id: int, verification_time: datetime) -> str:
        if not self.scheduler:
            raise VerificationServiceError("Scheduler not initialized")
        
        job_id = f"verify_campaign_{campaign_id}"
        
        try:
            self.scheduler.add_job(
                self._verify_campaign_job,
                DateTrigger(run_date=verification_time),
                args=[campaign_id],
                id=job_id,
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"Scheduled verification for campaign {campaign_id} at {verification_time}")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to schedule verification for campaign {campaign_id}: {e}")
            raise VerificationServiceError(f"Scheduling failed: {e}")

    async def _verify_campaign_job(self, campaign_id: int):
        logger.info(f"Starting verification job for campaign {campaign_id}")
        
        try:
            result = await self._verify_single_campaign(campaign_id)
            
            if result['success']:
                if result['is_compliant']:
                    await self._process_successful_campaign(campaign_id)
                    logger.info(f"Campaign {campaign_id} verification successful - compliant")
                else:
                    await self._process_failed_campaign(campaign_id, "Post not pinned for required duration")
                    logger.info(f"Campaign {campaign_id} verification failed - non-compliant")
            else:
                await self._schedule_verification_retry(campaign_id, result.get('error', 'Unknown error'))
                
        except Exception as e:
            logger.error(f"Verification job failed for campaign {campaign_id}: {e}")
            await self._schedule_verification_retry(campaign_id, str(e))

    async def _verify_single_campaign(self, campaign_id: int) -> Dict[str, Any]:
        try:
            campaign = await self.campaign_service.get_campaign_by_id(campaign_id)
            if not campaign:
                return {'success': False, 'error': f'Campaign {campaign_id} not found'}
            
            if not campaign.assignment:
                return {'success': False, 'error': f'Campaign {campaign_id} has no assignment'}
            
            if not campaign.assignment.is_posted:
                return {'success': False, 'error': f'Campaign {campaign_id} not posted yet'}
            
            if campaign.assignment.is_verified:
                return {
                    'success': True,
                    'is_compliant': campaign.assignment.is_compliant,
                    'already_verified': True
                }
            
            verification_result = await self.posting_service.verify_campaign_compliance(
                self.bot, campaign.assignment.id
            )
            
            return {
                'success': True,
                'is_compliant': verification_result['is_compliant'],
                'already_verified': verification_result.get('already_verified', False),
                'verified_at': verification_result.get('verified_at'),
                'error': verification_result.get('error')
            }
            
        except Exception as e:
            logger.error(f"Error verifying campaign {campaign_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def _process_successful_campaign(self, campaign_id: int):
        try:
            await self.campaign_service.update_campaign_status(
                campaign_id, CampaignStatus.COMPLETED, self.bot
            )
            
            await self.escrow_service.release_funds(campaign_id)
            
            logger.info(f"Campaign {campaign_id} completed successfully - funds released")
            
        except Exception as e:
            logger.error(f"Error processing successful campaign {campaign_id}: {e}")
            raise

    async def _process_failed_campaign(self, campaign_id: int, reason: str):
        try:
            await self.campaign_service.update_campaign_status(
                campaign_id, CampaignStatus.FAILED, self.bot
            )
            
            await self.escrow_service.refund_funds(campaign_id)
            
            logger.info(f"Campaign {campaign_id} failed: {reason} - funds refunded")
            
        except Exception as e:
            logger.error(f"Error processing failed campaign {campaign_id}: {e}")
            raise

    async def _schedule_verification_retry(self, campaign_id: int, error_reason: str, retry_count: int = 1):
        max_retries = 3
        
        if retry_count > max_retries:
            logger.error(f"Max retries exceeded for campaign {campaign_id}, marking as failed")
            await self._process_failed_campaign(campaign_id, f"Verification failed after {max_retries} retries: {error_reason}")
            return
        
        retry_delay_minutes = retry_count * 10
        retry_time = datetime.utcnow() + timedelta(minutes=retry_delay_minutes)
        
        job_id = f"verify_campaign_{campaign_id}_retry_{retry_count}"
        
        try:
            self.scheduler.add_job(
                self._verify_campaign_retry_job,
                DateTrigger(run_date=retry_time),
                args=[campaign_id, retry_count + 1],
                id=job_id,
                replace_existing=True,
                max_instances=1
            )
            
            logger.warning(f"Scheduled retry {retry_count} for campaign {campaign_id} at {retry_time} due to: {error_reason}")
            
        except Exception as e:
            logger.error(f"Failed to schedule retry for campaign {campaign_id}: {e}")
            await self._process_failed_campaign(campaign_id, f"Retry scheduling failed: {e}")

    async def _verify_campaign_retry_job(self, campaign_id: int, retry_count: int):
        logger.info(f"Starting verification retry {retry_count} for campaign {campaign_id}")
        
        try:
            result = await self._verify_single_campaign(campaign_id)
            
            if result['success']:
                if result['is_compliant']:
                    await self._process_successful_campaign(campaign_id)
                    logger.info(f"Campaign {campaign_id} verification retry {retry_count} successful")
                else:
                    await self._process_failed_campaign(campaign_id, "Post not pinned for required duration")
                    logger.info(f"Campaign {campaign_id} verification retry {retry_count} failed - non-compliant")
            else:
                await self._schedule_verification_retry(campaign_id, result.get('error', 'Unknown error'), retry_count)
                
        except Exception as e:
            logger.error(f"Verification retry {retry_count} failed for campaign {campaign_id}: {e}")
            await self._schedule_verification_retry(campaign_id, str(e), retry_count)

    async def _periodic_verification_check(self):
        logger.debug("Running periodic verification check")
        
        try:
            assignments = await self.posting_service.get_assignments_for_verification()
            
            for assignment in assignments:
                if not assignment.campaign:
                    continue
                    
                campaign_id = assignment.campaign.id
                
                existing_job = self.scheduler.get_job(f"verify_campaign_{campaign_id}")
                if existing_job:
                    logger.debug(f"Verification job already scheduled for campaign {campaign_id}")
                    continue
                
                logger.info(f"Triggering immediate verification for overdue campaign {campaign_id}")
                await self._verify_campaign_job(campaign_id)
                
        except Exception as e:
            logger.error(f"Error in periodic verification check: {e}")

    async def _cleanup_expired_campaigns(self):
        logger.debug("Running expired campaigns cleanup")
        
        try:
            expired_campaigns = await self.campaign_service.get_expired_campaigns()
            
            for campaign in expired_campaigns:
                try:
                    await self.campaign_service.update_campaign_status(
                        campaign.id, CampaignStatus.CANCELLED, self.bot
                    )
                    
                    if campaign.assignment:
                        await self.escrow_service.refund_funds(campaign.id)
                    
                    logger.info(f"Cleaned up expired campaign {campaign.id}")
                    
                except Exception as e:
                    logger.error(f"Error cleaning up expired campaign {campaign.id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in expired campaigns cleanup: {e}")

    async def get_verification_status(self, campaign_id: int) -> Dict[str, Any]:
        try:
            campaign = await self.campaign_service.get_campaign_by_id(campaign_id)
            if not campaign:
                return {'error': f'Campaign {campaign_id} not found'}
            
            status = {
                'campaign_id': campaign_id,
                'campaign_status': campaign.status.value,
                'has_assignment': campaign.assignment is not None
            }
            
            if campaign.assignment:
                assignment = campaign.assignment
                status.update({
                    'assignment_id': assignment.id,
                    'is_posted': assignment.is_posted,
                    'message_id': assignment.message_id,
                    'posted_at': assignment.posted_at,
                    'verification_scheduled_at': assignment.verification_scheduled_at,
                    'is_verified': assignment.is_verified,
                    'is_compliant': assignment.is_compliant,
                    'settlement_processed': assignment.settlement_processed
                })
                
                job_id = f"verify_campaign_{campaign_id}"
                scheduled_job = self.scheduler.get_job(job_id) if self.scheduler else None
                status['has_scheduled_verification'] = scheduled_job is not None
                
                if scheduled_job:
                    status['next_verification_run'] = scheduled_job.next_run_time
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting verification status for campaign {campaign_id}: {e}")
            return {'error': str(e)}

    async def force_verification(self, campaign_id: int) -> Dict[str, Any]:
        logger.info(f"Force verification requested for campaign {campaign_id}")
        
        try:
            result = await self._verify_single_campaign(campaign_id)
            
            if result['success'] and not result.get('already_verified', False):
                if result['is_compliant']:
                    await self._process_successful_campaign(campaign_id)
                else:
                    await self._process_failed_campaign(campaign_id, "Manual verification - post not pinned")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in force verification for campaign {campaign_id}: {e}")
            return {'success': False, 'error': str(e)}

    def get_scheduler_status(self) -> Dict[str, Any]:
        if not self.scheduler:
            return {'running': False, 'jobs': []}
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time,
                'trigger': str(job.trigger)
            })
        
        return {
            'running': self.scheduler.running,
            'job_count': len(jobs),
            'jobs': jobs
        }

    async def get_pending_verifications(self) -> List[Dict[str, Any]]:
        """Get list of campaigns pending verification."""
        try:
            campaigns = await self.campaign_service.get_campaigns_for_monitoring()
            
            pending = []
            for campaign in campaigns:
                if campaign.assignment:
                    pending.append({
                        'campaign_id': campaign.id,
                        'assignment_id': campaign.assignment.id,
                        'channel_name': campaign.assignment.channel.channel_name if campaign.assignment.channel else 'Unknown',
                        'posted_at': campaign.assignment.posted_at,
                        'verification_scheduled_at': campaign.assignment.verification_scheduled_at,
                        'message_id': campaign.assignment.message_id,
                        'price': float(campaign.price)
                    })
            
            return pending
            
        except Exception as e:
            logger.error(f"Error getting pending verifications: {e}")
            return []

    async def cancel_verification(self, campaign_id: int) -> bool:
        """Cancel a scheduled verification job."""
        if not self.scheduler:
            return False
        
        job_id = f"verify_campaign_{campaign_id}"
        
        try:
            job = self.scheduler.get_job(job_id)
            if job:
                job.remove()
                logger.info(f"Cancelled verification job for campaign {campaign_id}")
                return True
            else:
                logger.warning(f"No verification job found for campaign {campaign_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling verification for campaign {campaign_id}: {e}")
            return False