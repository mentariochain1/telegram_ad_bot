from typing import Optional
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from telegram_ad_bot.models.campaign import Campaign, CampaignStatus
from telegram_ad_bot.models.user import User
from telegram_ad_bot.models.channel import Channel
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class NotificationServiceError(Exception):
    pass


class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_campaign_accepted(self, campaign: Campaign, channel: Channel) -> bool:
        try:
            await self.bot.send_message(
                campaign.advertiser.telegram_id,
                f"🎉 <b>Campaign Accepted!</b>\n\n"
                f"Your campaign #{campaign.id} has been accepted by <b>{channel.channel_name}</b>.\n\n"
                f"💰 <b>Price:</b> ${campaign.price}\n"
                f"📺 <b>Channel:</b> {channel.channel_name}\n"
                f"💳 <b>Funds Status:</b> Held in escrow\n\n"
                f"The ad will be posted and pinned shortly. You'll be notified when it's live!",
                parse_mode="HTML"
            )
            logger.info(f"Sent campaign acceptance notification for campaign {campaign.id}")
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to send campaign acceptance notification: {e}")
            return False

    async def notify_campaign_posted(self, campaign: Campaign, channel: Channel, message_id: int) -> bool:
        try:
            await self.bot.send_message(
                campaign.advertiser.telegram_id,
                f"📢 <b>Ad Posted!</b>\n\n"
                f"Your campaign #{campaign.id} is now live on <b>{channel.channel_name}</b>!\n\n"
                f"📌 The ad has been pinned for {campaign.duration_hours} hour(s).\n"
                f"🔍 Monitoring will begin to ensure compliance.\n\n"
                f"You'll be notified when the campaign completes.",
                parse_mode="HTML"
            )

            await self.bot.send_message(
                channel.owner.telegram_id,
                f"✅ <b>Ad Posted Successfully!</b>\n\n"
                f"Campaign #{campaign.id} has been posted to your channel <b>{channel.channel_name}</b>.\n\n"
                f"💰 <b>Earnings:</b> ${campaign.price}\n"
                f"⏱ <b>Duration:</b> {campaign.duration_hours} hour(s)\n\n"
                f"Keep the ad pinned for the full duration to receive payment!",
                parse_mode="HTML"
            )
            logger.info(f"Sent campaign posted notifications for campaign {campaign.id}")
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to send campaign posted notification: {e}")
            return False

    async def notify_campaign_completed(self, campaign: Campaign, channel: Channel, payment_amount: float) -> bool:
        try:
            await self.bot.send_message(
                campaign.advertiser.telegram_id,
                f"✅ <b>Campaign Completed!</b>\n\n"
                f"Your campaign #{campaign.id} on <b>{channel.channel_name}</b> has completed successfully.\n\n"
                f"💰 <b>Payment:</b> ${campaign.price} has been released to the channel owner.\n"
                f"📊 The ad remained pinned for the full duration.\n\n"
                f"Thank you for using AdPost Bot!",
                parse_mode="HTML"
            )

            await self.bot.send_message(
                channel.owner.telegram_id,
                f"💰 <b>Payment Received!</b>\n\n"
                f"Campaign #{campaign.id} completed successfully!\n\n"
                f"💵 <b>Earned:</b> ${payment_amount}\n"
                f"📺 <b>Channel:</b> {channel.channel_name}\n"
                f"✅ <b>Status:</b> Payment processed\n\n"
                f"The funds have been added to your balance. Great job!",
                parse_mode="HTML"
            )
            logger.info(f"Sent campaign completion notifications for campaign {campaign.id}")
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to send campaign completion notification: {e}")
            return False

    async def notify_campaign_failed(self, campaign: Campaign, channel: Channel, reason: str) -> bool:
        try:
            await self.bot.send_message(
                campaign.advertiser.telegram_id,
                f"❌ <b>Campaign Failed</b>\n\n"
                f"Your campaign #{campaign.id} on <b>{channel.channel_name}</b> did not complete successfully.\n\n"
                f"📋 <b>Reason:</b> {reason}\n"
                f"💰 <b>Refund:</b> ${campaign.price} has been returned to your balance.\n\n"
                f"You can create a new campaign anytime.",
                parse_mode="HTML"
            )

            await self.bot.send_message(
                channel.owner.telegram_id,
                f"⚠️ <b>Campaign Failed</b>\n\n"
                f"Campaign #{campaign.id} did not complete successfully.\n\n"
                f"📋 <b>Reason:</b> {reason}\n"
                f"💰 <b>Payment:</b> Not processed (refunded to advertiser)\n\n"
                f"Please ensure ads remain pinned for the full duration to receive payment.",
                parse_mode="HTML"
            )
            logger.info(f"Sent campaign failure notifications for campaign {campaign.id}")
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to send campaign failure notification: {e}")
            return False

    async def notify_balance_update(self, user: User, amount: float, transaction_type: str, description: str) -> bool:
        try:
            emoji_map = {
                'deposit': '💰',
                'payment': '💵',
                'refund': '🔄',
                'hold': '🔒'
            }
            
            emoji = emoji_map.get(transaction_type.lower(), '💳')
            
            await self.bot.send_message(
                user.telegram_id,
                f"{emoji} <b>Balance Update</b>\n\n"
                f"💳 <b>Transaction:</b> {description}\n"
                f"💰 <b>Amount:</b> ${abs(amount)}\n"
                f"💵 <b>New Balance:</b> ${user.balance}\n",
                parse_mode="HTML"
            )
            logger.info(f"Sent balance update notification to user {user.id}")
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to send balance update notification: {e}")
            return False

    async def notify_error(self, user_id: int, error_message: str, context: Optional[str] = None) -> bool:
        try:
            message = f"⚠️ <b>Error Notification</b>\n\n{error_message}"
            if context:
                message += f"\n\n<i>Context: {context}</i>"
            
            await self.bot.send_message(user_id, message, parse_mode="HTML")
            logger.info(f"Sent error notification to user {user_id}")
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to send error notification: {e}")
            return False