"""Refactored bot handlers with improved structure and maintainability."""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from telegram_ad_bot.handlers.helpers import (
    get_main_menu_keyboard, format_campaign_summary, format_channel_summary
)
from telegram_ad_bot.handlers.error_handlers import (
    handle_user_service_error, handle_channel_service_error,
    handle_campaign_service_error, handle_unexpected_error
)
from telegram_ad_bot.services.user_service import UserService, UserServiceError
from telegram_ad_bot.services.channel_service import ChannelService, ChannelServiceError
from telegram_ad_bot.services.campaign_service import CampaignService, CampaignServiceError
from telegram_ad_bot.models.user import UserRole
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)

router = Router()


@router.callback_query(F.data == "check_balance")
async def check_balance(callback_query: CallbackQuery):
    """Check user balance and show options."""
    try:
        user = await _get_user_from_callback(callback_query)
        if not user:
            return
        
        keyboard = _get_balance_keyboard(user.role)
        await callback_query.message.edit_text(
            f"💳 Your Balance: ${user.balance}\n\n"
            "Note: This is a prototype using virtual currency.\n"
            "In production, this would integrate with real payment systems.",
            reply_markup=keyboard
        )
        await callback_query.answer()
        
    except UserServiceError as e:
        await handle_user_service_error(callback_query, e, "balance check")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "balance check")


def _get_balance_keyboard(user_role: UserRole) -> InlineKeyboardMarkup:
    """Get appropriate keyboard for balance screen."""
    if user_role == UserRole.ADVERTISER:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Add Test Funds (+$100)", callback_data="add_test_funds")],
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
        ])
    else:
        return get_main_menu_keyboard(user_role)


@router.callback_query(F.data == "my_campaigns")
async def show_my_campaigns(callback_query: CallbackQuery):
    """Show user's campaigns."""
    try:
        user = await _get_user_from_callback(callback_query)
        if not user:
            return
        
        campaigns = await _get_user_campaigns(user.id)
        await _display_campaigns(callback_query, campaigns, user.role)
        
    except (UserServiceError, CampaignServiceError) as e:
        await handle_campaign_service_error(callback_query, e, "campaigns display")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "campaigns display")


async def _get_user_campaigns(user_id: int):
    """Get campaigns for a user."""
    campaign_service = CampaignService()
    return await campaign_service.get_campaigns_by_advertiser(user_id)


async def _display_campaigns(callback_query: CallbackQuery, campaigns, user_role: UserRole):
    """Display campaigns list to user."""
    keyboard = get_main_menu_keyboard(user_role)
    
    if not campaigns:
        await callback_query.message.edit_text(
            "You haven't created any campaigns yet.\n\n"
            "Create your first campaign to get started!",
            reply_markup=keyboard
        )
        return
    
    campaign_list = [format_campaign_summary(campaign) for campaign in campaigns[:10]]
    
    await callback_query.message.edit_text(
        f"<b>Your Campaigns ({len(campaigns)} total):</b>\n\n" + 
        "\n\n".join(campaign_list),
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "browse_campaigns")
async def browse_campaigns(callback_query: CallbackQuery):
    """Browse available campaigns for channel owners."""
    try:
        user = await _get_user_from_callback(callback_query)
        if not user or user.role != UserRole.CHANNEL_OWNER:
            await callback_query.answer("Access denied. Channel owners only.", show_alert=True)
            return
        
        campaigns = await _get_available_campaigns()
        await _display_available_campaigns(callback_query, campaigns, user.role)
        
    except (UserServiceError, CampaignServiceError) as e:
        await handle_campaign_service_error(callback_query, e, "campaign browsing")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "campaign browsing")


async def _get_available_campaigns():
    """Get available campaigns."""
    campaign_service = CampaignService()
    return await campaign_service.get_available_campaigns()


async def _display_available_campaigns(callback_query: CallbackQuery, campaigns, user_role: UserRole):
    """Display available campaigns to channel owner."""
    if not campaigns:
        keyboard = get_main_menu_keyboard(user_role)
        await callback_query.message.edit_text(
            "No campaigns available right now.\n\n"
            "Check back later for new advertising opportunities!",
            reply_markup=keyboard
        )
        return
    
    keyboard = _build_campaigns_keyboard(campaigns)
    await callback_query.message.edit_text(
        f"<b>Available Campaigns ({len(campaigns)} total):</b>\n\n"
        "Select a campaign to view details and accept it:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


def _build_campaigns_keyboard(campaigns) -> InlineKeyboardMarkup:
    """Build keyboard for campaign selection."""
    keyboard_buttons = []
    
    for campaign in campaigns[:5]:
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"💰 ${campaign.price} - Campaign {campaign.id}",
                callback_data=f"view_campaign_{campaign.id}"
            )
        ])
    
    keyboard_buttons.extend([
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="browse_campaigns")],
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)


@router.callback_query(F.data == "my_channels")
async def show_my_channels(callback_query: CallbackQuery):
    """Show user's channels."""
    try:
        user = await _get_user_from_callback(callback_query)
        if not user or user.role != UserRole.CHANNEL_OWNER:
            await callback_query.answer("Access denied. Channel owners only.", show_alert=True)
            return
        
        channels = await _get_user_channels(user.id)
        await _display_channels(callback_query, channels, user.role)
        
    except (UserServiceError, ChannelServiceError) as e:
        await handle_channel_service_error(callback_query, e, "channels display")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "channels display")


async def _get_user_channels(user_id: int):
    """Get channels for a user."""
    channel_service = ChannelService()
    return await channel_service.get_channels_by_owner(user_id)


async def _display_channels(callback_query: CallbackQuery, channels, user_role: UserRole):
    """Display channels list to user."""
    keyboard = get_main_menu_keyboard(user_role)
    
    if not channels:
        await callback_query.message.edit_text(
            "You haven't registered any channels yet.\n\n"
            "Use /start to register your first channel!",
            reply_markup=keyboard
        )
        return
    
    channel_list = [format_channel_summary(channel) for channel in channels]
    
    await callback_query.message.edit_text(
        f"<b>Your Channels ({len(channels)} total):</b>\n\n" + 
        "\n\n".join(channel_list),
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "add_test_funds")
async def add_test_funds(callback_query: CallbackQuery):
    """Add test funds to user account."""
    try:
        user_service = UserService()
        user = await user_service.get_user_by_telegram_id(callback_query.from_user.id)
        
        if not user:
            await callback_query.answer("User not found. Please start over with /start", show_alert=True)
            return
        
        await user_service.add_balance(user.id, 100.00)
        
        keyboard = get_main_menu_keyboard(user.role)
        await callback_query.message.edit_text(
            f"💰 Test funds added!\n\n"
            f"Your new balance: ${user.balance + 100.00}\n\n"
            "Note: This is prototype functionality. In production, this would integrate with real payment systems.",
            reply_markup=keyboard
        )
        await callback_query.answer("$100 added to your balance!")
        
    except UserServiceError as e:
        await handle_user_service_error(callback_query, e, "add test funds")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "add test funds")


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: CallbackQuery):
    """Return to main menu."""
    try:
        user = await _get_user_from_callback(callback_query)
        if not user:
            return
        
        keyboard = get_main_menu_keyboard(user.role)
        role_text = "Advertiser" if user.role == UserRole.ADVERTISER else "Channel Owner"
        
        await callback_query.message.edit_text(
            f"Welcome back! You're registered as a {role_text}.\n\n"
            f"Your current balance: ${user.balance}\n\n"
            "What would you like to do?",
            reply_markup=keyboard
        )
        await callback_query.answer()
        
    except UserServiceError as e:
        await handle_user_service_error(callback_query, e, "back to menu")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "back to menu")


@router.message()
async def handle_unknown_message(message: Message, state: FSMContext):
    """Handle unknown messages."""
    try:
        current_state = await state.get_state()
        if current_state:
            await message.answer("I didn't understand that. Please follow the current process or use /start to begin again.")
        else:
            await message.answer("I didn't understand that command. Use /start to begin.")
            
    except Exception as e:
        await handle_unexpected_error(message, e, "unknown message handling", state)


async def _get_user_from_callback(callback_query: CallbackQuery):
    """Get user from callback query."""
    user_service = UserService()
    user = await user_service.get_user_by_telegram_id(callback_query.from_user.id)
    
    if not user:
        await callback_query.answer("User not found. Please start over with /start", show_alert=True)
        return None
    
    return user