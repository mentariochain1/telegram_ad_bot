"""Helper functions for bot handlers to reduce code duplication and improve maintainability."""

from typing import Optional, Tuple
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from telegram_ad_bot.models.user import UserRole
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


def get_role_selection_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for role selection during registration."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Advertiser", callback_data="role_advertiser")],
        [InlineKeyboardButton(text="📺 Channel Owner", callback_data="role_channel_owner")]
    ])


def get_main_menu_keyboard(user_role: UserRole) -> InlineKeyboardMarkup:
    """Create main menu keyboard based on user role."""
    if user_role == UserRole.ADVERTISER:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Create Campaign", callback_data="create_campaign")],
            [InlineKeyboardButton(text="📊 My Campaigns", callback_data="my_campaigns")],
            [InlineKeyboardButton(text="💳 Balance", callback_data="check_balance")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Browse Campaigns", callback_data="browse_campaigns")],
            [InlineKeyboardButton(text="📺 My Channels", callback_data="my_channels")],
            [InlineKeyboardButton(text="⚙️ Channel Setup", callback_data="channel_setup")],
            [InlineKeyboardButton(text="💳 Balance", callback_data="check_balance")]
        ])


def get_campaign_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for campaign confirmation."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Create Campaign", callback_data="confirm_campaign")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_campaign")]
    ])


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Create simple back to menu keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
    ])


async def extract_channel_info_from_message(message: Message) -> Tuple[Optional[str], Optional[str]]:
    """Extract channel ID and name from forwarded message or username."""
    channel_id = None
    channel_name = None
    
    if message.forward_from_chat:
        if message.forward_from_chat.type in ["channel", "supergroup"]:
            channel_id = str(message.forward_from_chat.id)
            channel_name = message.forward_from_chat.title or message.forward_from_chat.username
        else:
            await message.answer("Please forward a message from a channel, not a private chat or group.")
            return None, None
            
    elif message.text and message.text.startswith("@"):
        channel_username = message.text.strip()
        try:
            chat = await message.bot.get_chat(channel_username)
            if chat.type in ["channel", "supergroup"]:
                channel_id = str(chat.id)
                channel_name = chat.title or chat.username
            else:
                await message.answer("This doesn't appear to be a channel. Please provide a channel username.")
                return None, None
        except TelegramBadRequest:
            await message.answer("I couldn't find that channel. Please check the username and try again.")
            return None, None
    else:
        await message.answer(
            "Please either:\n"
            "• Send your channel username (e.g., @mychannel)\n"
            "• Forward a message from your channel"
        )
        return None, None
    
    return channel_id, channel_name


async def verify_user_is_channel_admin(message: Message, channel_id: str) -> bool:
    """Verify that the user is an admin of the specified channel."""
    try:
        chat_member = await message.bot.get_chat_member(channel_id, message.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await message.answer(
                "You need to be an admin of this channel to register it.\n"
                "Please make sure you have admin rights and try again."
            )
            return False
        return True
    except TelegramBadRequest:
        await message.answer(
            "I couldn't verify your admin status. Please make sure:\n"
            "• You're an admin of the channel\n"
            "• The channel is public or I have access to it"
        )
        return False


async def check_bot_permissions_in_channel(message: Message, channel_id: str) -> Tuple[bool, bool, bool]:
    """Check if bot has required permissions in the channel."""
    try:
        bot_member = await message.bot.get_chat_member(channel_id, (await message.bot.get_me()).id)
        
        is_admin = bot_member.status == "administrator"
        can_post = bot_member.can_post_messages if hasattr(bot_member, 'can_post_messages') else True
        can_pin = bot_member.can_pin_messages if hasattr(bot_member, 'can_pin_messages') else True
        
        return is_admin, can_post, can_pin
    except TelegramBadRequest as e:
        logger.error(f"Error checking bot permissions: {e}")
        return False, False, False


def format_campaign_summary(campaign) -> str:
    """Format campaign information for display."""
    status_emoji = {
        "PENDING": "⏳",
        "ACTIVE": "🟢", 
        "COMPLETED": "✅",
        "FAILED": "❌",
        "CANCELLED": "🚫"
    }.get(campaign.status.value, "❓")
    
    channel_info = ""
    if campaign.assignment and campaign.assignment.channel:
        channel_info = f"\nChannel: {campaign.assignment.channel.channel_name}"
    
    ad_text = campaign.ad_text[:50] + ('...' if len(campaign.ad_text) > 50 else '')
    
    return (
        f"{status_emoji} <b>Campaign {campaign.id}</b>\n"
        f"Status: {campaign.status.value.title()}\n"
        f"Price: ${campaign.price}{channel_info}\n"
        f"Text: {ad_text}"
    )


def format_channel_summary(channel) -> str:
    """Format channel information for display."""
    status_emoji = "✅" if channel.is_ready_for_ads else "⚠️"
    status_text = "Ready" if channel.is_ready_for_ads else "Setup needed"
    
    return (
        f"{status_emoji} <b>{channel.channel_name}</b>\n"
        f"Status: {status_text}\n"
        f"Verified: {'Yes' if channel.is_verified else 'No'}\n"
        f"Bot Admin: {'Yes' if channel.bot_admin_status else 'No'}"
    )