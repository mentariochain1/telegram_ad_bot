from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from telegram_ad_bot.models.channel import Channel
from telegram_ad_bot.models.user import User, UserRole
from telegram_ad_bot.models.campaign import Campaign, CampaignAssignment
from telegram_ad_bot.database.connection import create_db_session
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


class ChannelServiceError(Exception):
    pass


class ChannelNotFoundError(ChannelServiceError):
    pass


class InvalidOwnerError(ChannelServiceError):
    pass


class ChannelAlreadyExistsError(ChannelServiceError):
    pass


class BotPermissionError(ChannelServiceError):
    pass


class PostingError(ChannelServiceError):
    pass


class PinningError(ChannelServiceError):
    pass


class ChannelService:
    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> AsyncSession:
        if self._session:
            return self._session
        return await create_db_session()

    async def register_channel(self, owner_id: int, telegram_channel_id: str, 
                             channel_name: str, subscriber_count: int = 0) -> Channel:
        session = await self._get_session()
        try:
            owner = await session.get(User, owner_id)
            if not owner:
                raise InvalidOwnerError(f"Owner {owner_id} not found")
            
            if not owner.is_channel_owner:
                raise InvalidOwnerError(f"User {owner_id} is not a channel owner")

            existing_channel = await self.get_channel_by_telegram_id(telegram_channel_id)
            if existing_channel:
                raise ChannelAlreadyExistsError(f"Channel {telegram_channel_id} already registered")

            channel = Channel(
                telegram_channel_id=telegram_channel_id,
                channel_name=channel_name,
                subscriber_count=subscriber_count,
                owner_id=owner_id,
                is_verified=False,
                bot_admin_status=False
            )
            
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
            
            logger.info(f"Registered channel {telegram_channel_id} for owner {owner_id}")
            return channel
            
        except (InvalidOwnerError, ChannelAlreadyExistsError):
            await session.rollback()
            raise
        except IntegrityError as e:
            await session.rollback()
            logger.error(f"Failed to register channel {telegram_channel_id}: {e}")
            raise ChannelServiceError(f"Channel registration failed: {e}")
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error during channel registration: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_channel_by_telegram_id(self, telegram_channel_id: str) -> Optional[Channel]:
        session = await self._get_session()
        try:
            stmt = select(Channel).where(Channel.telegram_channel_id == telegram_channel_id)
            result = await session.execute(stmt)
            channel = result.scalar_one_or_none()
            
            if channel:
                logger.debug(f"Found channel: {telegram_channel_id}")
            else:
                logger.debug(f"Channel not found: {telegram_channel_id}")
            
            return channel
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting channel {telegram_channel_id}: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_channel_by_id(self, channel_id: int) -> Optional[Channel]:
        session = await self._get_session()
        try:
            channel = await session.get(Channel, channel_id)
            
            if channel:
                logger.debug(f"Found channel by ID: {channel_id}")
            else:
                logger.debug(f"Channel not found by ID: {channel_id}")
            
            return channel
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting channel by ID {channel_id}: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_channels_by_owner(self, owner_id: int) -> List[Channel]:
        session = await self._get_session()
        try:
            stmt = select(Channel).where(Channel.owner_id == owner_id)
            result = await session.execute(stmt)
            channels = result.scalars().all()
            
            logger.debug(f"Found {len(channels)} channels for owner {owner_id}")
            return list(channels)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting channels for owner {owner_id}: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def verify_channel(self, channel_id: int, is_verified: bool = True) -> Channel:
        session = await self._get_session()
        try:
            channel = await session.get(Channel, channel_id)
            if not channel:
                raise ChannelNotFoundError(f"Channel {channel_id} not found")

            channel.is_verified = is_verified
            await session.commit()
            await session.refresh(channel)
            
            logger.info(f"Channel {channel_id} verification status updated to {is_verified}")
            return channel
            
        except ChannelNotFoundError:
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error verifying channel: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def update_bot_admin_status(self, channel_id: int, has_admin: bool) -> Channel:
        session = await self._get_session()
        try:
            channel = await session.get(Channel, channel_id)
            if not channel:
                raise ChannelNotFoundError(f"Channel {channel_id} not found")

            channel.bot_admin_status = has_admin
            await session.commit()
            await session.refresh(channel)
            
            logger.info(f"Channel {channel_id} bot admin status updated to {has_admin}")
            return channel
            
        except ChannelNotFoundError:
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error updating bot admin status: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def update_subscriber_count(self, channel_id: int, subscriber_count: int) -> Channel:
        session = await self._get_session()
        try:
            channel = await session.get(Channel, channel_id)
            if not channel:
                raise ChannelNotFoundError(f"Channel {channel_id} not found")

            old_count = channel.subscriber_count
            channel.subscriber_count = subscriber_count
            await session.commit()
            await session.refresh(channel)
            
            logger.info(f"Channel {channel_id} subscriber count updated: {old_count} -> {subscriber_count}")
            return channel
            
        except ChannelNotFoundError:
            raise
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error updating subscriber count: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def get_ready_channels(self) -> List[Channel]:
        session = await self._get_session()
        try:
            stmt = select(Channel).where(
                Channel.is_verified == True,
                Channel.bot_admin_status == True
            )
            result = await session.execute(stmt)
            channels = result.scalars().all()
            
            logger.debug(f"Found {len(channels)} channels ready for ads")
            return list(channels)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting ready channels: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def delete_channel(self, channel_id: int) -> bool:
        session = await self._get_session()
        try:
            channel = await session.get(Channel, channel_id)
            if not channel:
                return False

            await session.delete(channel)
            await session.commit()
            
            logger.info(f"Deleted channel {channel_id}")
            return True
            
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error deleting channel: {e}")
            raise ChannelServiceError(f"Database error: {e}")
        finally:
            if self._owns_session:
                await session.close()

    async def verify_bot_permissions(self, bot: Bot, channel_id: str) -> Dict[str, Any]:
        try:
            bot_info = await bot.get_me()
            chat_member = await bot.get_chat_member(channel_id, bot_info.id)
            
            permissions = {
                'is_admin': chat_member.status == 'administrator',
                'can_post_messages': False,
                'can_pin_messages': False,
                'can_delete_messages': False,
                'status': chat_member.status
            }
            
            if chat_member.status == 'administrator':
                permissions['can_post_messages'] = getattr(chat_member, 'can_post_messages', True)
                permissions['can_pin_messages'] = getattr(chat_member, 'can_pin_messages', True)
                permissions['can_delete_messages'] = getattr(chat_member, 'can_delete_messages', True)
            
            logger.debug(f"Bot permissions for channel {channel_id}: {permissions}")
            return permissions
            
        except TelegramBadRequest as e:
            logger.error(f"Bad request checking bot permissions for {channel_id}: {e}")
            raise BotPermissionError(f"Cannot access channel: {e}")
        except TelegramForbiddenError as e:
            logger.error(f"Forbidden checking bot permissions for {channel_id}: {e}")
            raise BotPermissionError(f"Bot not authorized: {e}")
        except TelegramAPIError as e:
            logger.error(f"Telegram API error checking permissions for {channel_id}: {e}")
            raise BotPermissionError(f"API error: {e}")

    async def post_ad_to_channel(self, bot: Bot, channel_id: str, ad_text: str, 
                               campaign_id: int) -> Message:
        try:
            permissions = await self.verify_bot_permissions(bot, channel_id)
            
            if not permissions['is_admin']:
                raise BotPermissionError(f"Bot is not admin in channel {channel_id}")
            
            if not permissions['can_post_messages']:
                raise BotPermissionError(f"Bot cannot post messages in channel {channel_id}")
            
            formatted_message = self._format_ad_message(ad_text, campaign_id)
            
            message = await bot.send_message(
                chat_id=channel_id,
                text=formatted_message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
            logger.info(f"Posted ad to channel {channel_id}, message ID: {message.message_id}")
            return message
            
        except BotPermissionError:
            raise
        except TelegramBadRequest as e:
            logger.error(f"Bad request posting to channel {channel_id}: {e}")
            raise PostingError(f"Failed to post message: {e}")
        except TelegramForbiddenError as e:
            logger.error(f"Forbidden posting to channel {channel_id}: {e}")
            raise PostingError(f"Not authorized to post: {e}")
        except TelegramAPIError as e:
            logger.error(f"Telegram API error posting to channel {channel_id}: {e}")
            raise PostingError(f"API error: {e}")

    async def pin_message(self, bot: Bot, channel_id: str, message_id: int) -> bool:
        try:
            permissions = await self.verify_bot_permissions(bot, channel_id)
            
            if not permissions['can_pin_messages']:
                raise BotPermissionError(f"Bot cannot pin messages in channel {channel_id}")
            
            await bot.pin_chat_message(
                chat_id=channel_id,
                message_id=message_id,
                disable_notification=True
            )
            
            logger.info(f"Pinned message {message_id} in channel {channel_id}")
            return True
            
        except BotPermissionError:
            raise
        except TelegramBadRequest as e:
            logger.error(f"Bad request pinning message in channel {channel_id}: {e}")
            raise PinningError(f"Failed to pin message: {e}")
        except TelegramForbiddenError as e:
            logger.error(f"Forbidden pinning message in channel {channel_id}: {e}")
            raise PinningError(f"Not authorized to pin: {e}")
        except TelegramAPIError as e:
            logger.error(f"Telegram API error pinning message in channel {channel_id}: {e}")
            raise PinningError(f"API error: {e}")

    async def post_and_pin_ad(self, bot: Bot, channel_id: str, ad_text: str, 
                            campaign_id: int) -> Dict[str, Any]:
        try:
            message = await self.post_ad_to_channel(bot, channel_id, ad_text, campaign_id)
            
            try:
                await self.pin_message(bot, channel_id, message.message_id)
                pinned = True
                pin_error = None
            except (BotPermissionError, PinningError) as e:
                logger.warning(f"Failed to pin message in channel {channel_id}: {e}")
                pinned = False
                pin_error = str(e)
            
            result = {
                'message_id': message.message_id,
                'posted_at': datetime.utcnow(),
                'pinned': pinned,
                'pin_error': pin_error
            }
            
            logger.info(f"Ad posting result for channel {channel_id}: {result}")
            return result
            
        except (BotPermissionError, PostingError) as e:
            logger.error(f"Failed to post ad to channel {channel_id}: {e}")
            raise

    async def verify_message_pinned(self, bot: Bot, channel_id: str, message_id: int) -> bool:
        try:
            chat = await bot.get_chat(channel_id)
            
            if hasattr(chat, 'pinned_message') and chat.pinned_message:
                is_pinned = chat.pinned_message.message_id == message_id
                logger.debug(f"Message {message_id} pinned status in {channel_id}: {is_pinned}")
                return is_pinned
            
            logger.debug(f"No pinned message found in channel {channel_id}")
            return False
            
        except TelegramAPIError as e:
            logger.error(f"Error checking pinned message in {channel_id}: {e}")
            raise BotPermissionError(f"Cannot verify pinned status: {e}")

    async def get_channel_admin_guidance(self, bot: Bot, channel_id: str) -> Dict[str, Any]:
        try:
            permissions = await self.verify_bot_permissions(bot, channel_id)
            bot_info = await bot.get_me()
            
            guidance = {
                'bot_username': bot_info.username,
                'is_admin': permissions['is_admin'],
                'missing_permissions': [],
                'setup_complete': True,
                'instructions': []
            }
            
            if not permissions['is_admin']:
                guidance['setup_complete'] = False
                guidance['instructions'].append(
                    f"1. Add @{bot_info.username} as an administrator to your channel"
                )
            else:
                if not permissions['can_post_messages']:
                    guidance['missing_permissions'].append('Post messages')
                    guidance['setup_complete'] = False
                
                if not permissions['can_pin_messages']:
                    guidance['missing_permissions'].append('Pin messages')
                    guidance['setup_complete'] = False
                
                if guidance['missing_permissions']:
                    guidance['instructions'].append(
                        f"2. Grant the following permissions to @{bot_info.username}:"
                    )
                    for perm in guidance['missing_permissions']:
                        guidance['instructions'].append(f"   • {perm}")
            
            if guidance['setup_complete']:
                guidance['instructions'] = ["✅ Channel setup is complete! Ready to receive ads."]
            
            return guidance
            
        except BotPermissionError as e:
            return {
                'bot_username': (await bot.get_me()).username,
                'is_admin': False,
                'missing_permissions': ['All permissions'],
                'setup_complete': False,
                'instructions': [
                    f"1. Add @{(await bot.get_me()).username} as an administrator",
                    "2. Grant permissions to post and pin messages",
                    f"Error details: {e}"
                ]
            }

    def _format_ad_message(self, ad_text: str, campaign_id: int) -> str:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        formatted_message = f"""📢 <b>Sponsored Content</b>

{ad_text}

<i>Campaign ID: {campaign_id} | Posted: {timestamp}</i>"""
        
        return formatted_message