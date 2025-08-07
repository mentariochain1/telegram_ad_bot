"""Campaign-related handlers for creating and managing ad campaigns."""

from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from telegram_ad_bot.handlers.states import CampaignStates
from telegram_ad_bot.handlers.helpers import get_main_menu_keyboard, get_campaign_confirmation_keyboard
from telegram_ad_bot.handlers.error_handlers import (
    handle_user_service_error, handle_campaign_service_error,
    handle_telegram_api_error, handle_unexpected_error, safe_state_clear
)
from telegram_ad_bot.services.user_service import UserService, UserServiceError
from telegram_ad_bot.services.campaign_service import CampaignService, CampaignServiceError, CampaignValidationError, InsufficientBalanceError
from telegram_ad_bot.models.user import UserRole
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)

router = Router()


@router.callback_query(F.data == "create_campaign")
async def start_campaign_creation(callback_query: CallbackQuery, state: FSMContext):
    """Start the campaign creation process."""
    try:
        await callback_query.message.edit_text(
            "Let's create your ad campaign! 📢\n\n"
            "First, please send me the text for your advertisement.\n"
            "Keep it engaging and clear - this is what channel owners will see."
        )
        await state.set_state(CampaignStates.waiting_for_ad_text)
        await callback_query.answer()
        
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "campaign creation start", state)


@router.message(StateFilter(CampaignStates.waiting_for_ad_text))
async def handle_campaign_ad_text(message: Message, state: FSMContext):
    """Handle ad text input for campaign creation."""
    try:
        ad_text = message.text.strip()
        
        if not _is_valid_ad_text(ad_text):
            return
        
        await state.update_data(ad_text=ad_text)
        await _show_ad_text_confirmation(message, ad_text, state)
        
    except Exception as e:
        await handle_unexpected_error(message, e, "campaign ad text", state)


def _is_valid_ad_text(ad_text: str) -> bool:
    """Validate ad text input."""
    if not ad_text:
        return False
    if len(ad_text) > 1000:
        return False
    return True


async def _show_ad_text_confirmation(message: Message, ad_text: str, state: FSMContext):
    """Show ad text confirmation and ask for price."""
    await message.answer(
        f"Great! Here's your ad text:\n\n"
        f"<blockquote>{ad_text}</blockquote>\n\n"
        "Now, please enter the price you want to pay for this campaign (in USD).\n"
        "Example: 10.50",
        parse_mode="HTML"
    )
    await state.set_state(CampaignStates.waiting_for_price)


@router.message(StateFilter(CampaignStates.waiting_for_price))
async def handle_campaign_price(message: Message, state: FSMContext):
    """Handle price input for campaign creation."""
    try:
        price = _parse_and_validate_price(message.text.strip())
        if price is None:
            return
        
        data = await state.get_data()
        ad_text = data.get("ad_text")
        
        await state.update_data(price=price)
        await _show_campaign_summary(message, state, ad_text, price)
        
    except Exception as e:
        await handle_unexpected_error(message, e, "campaign price", state)


def _parse_and_validate_price(price_text: str) -> Decimal:
    """Parse and validate price input."""
    try:
        price = Decimal(price_text)
        if price <= 0:
            return None
        if price > 10000:
            return None
        return price
    except (InvalidOperation, ValueError):
        return None


async def _show_campaign_summary(message: Message, state: FSMContext, ad_text: str, price: Decimal):
    """Show campaign summary and check user balance."""
    user_service = UserService()
    user = await user_service.get_user_by_telegram_id(message.from_user.id)
    
    if not user:
        await message.answer("User not found. Please start over with /start")
        await safe_state_clear(state, "campaign summary")
        return
    
    if user.balance < price:
        await _show_insufficient_balance_error(message, state, price, user.balance)
        return
    
    keyboard = get_campaign_confirmation_keyboard()
    await message.answer(
        f"Campaign Summary:\n\n"
        f"<b>Ad Text:</b>\n<blockquote>{ad_text}</blockquote>\n\n"
        f"<b>Price:</b> ${price}\n"
        f"<b>Duration:</b> 1 hour (pinned)\n"
        f"<b>Your Balance:</b> ${user.balance}\n\n"
        "Please confirm to create your campaign:",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.set_state(CampaignStates.waiting_for_confirmation)


async def _show_insufficient_balance_error(message: Message, state: FSMContext, price: Decimal, balance: Decimal):
    """Show insufficient balance error."""
    keyboard = get_main_menu_keyboard(UserRole.ADVERTISER)
    await message.answer(
        f"❌ <b>Insufficient Balance</b>\n\n"
        f"Campaign price: ${price}\n"
        f"Your balance: ${balance}\n"
        f"Needed: ${price - balance}\n\n"
        f"<i>Note: This is a prototype. In production, you would add funds through integrated payment systems.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.clear()


@router.callback_query(F.data == "confirm_campaign", StateFilter(CampaignStates.waiting_for_confirmation))
async def confirm_campaign_creation(callback_query: CallbackQuery, state: FSMContext):
    """Confirm and create the campaign."""
    try:
        data = await state.get_data()
        ad_text = data.get("ad_text")
        price = data.get("price")
        
        if not ad_text or not price:
            await callback_query.answer("Campaign data missing. Please start over.", show_alert=True)
            await safe_state_clear(state, "campaign confirmation")
            return
        
        user = await _get_user_for_campaign(callback_query, state)
        if not user:
            return
        
        await _create_and_show_campaign(callback_query, state, user, ad_text, price)
        
    except (CampaignValidationError, InsufficientBalanceError) as e:
        await handle_campaign_service_error(callback_query, e, "campaign creation")
    except (CampaignServiceError, UserServiceError) as e:
        await handle_campaign_service_error(callback_query, e, "campaign creation")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "campaign confirmation", state)


async def _get_user_for_campaign(callback_query: CallbackQuery, state: FSMContext):
    """Get user for campaign creation."""
    user_service = UserService()
    user = await user_service.get_user_by_telegram_id(callback_query.from_user.id)
    
    if not user:
        await callback_query.answer("User not found. Please start over with /start", show_alert=True)
        await safe_state_clear(state, "user lookup")
        return None
    
    return user


async def _create_and_show_campaign(callback_query: CallbackQuery, state: FSMContext, user, ad_text: str, price: Decimal):
    """Create campaign and show success message."""
    campaign_service = CampaignService()
    campaign = await campaign_service.create_campaign(
        advertiser_id=user.id,
        ad_text=ad_text,
        price=price
    )
    
    keyboard = get_main_menu_keyboard(UserRole.ADVERTISER)
    await callback_query.message.edit_text(
        f"Campaign created successfully! 🎉\n\n"
        f"<b>Campaign ID:</b> {campaign.id}\n"
        f"<b>Status:</b> Pending\n"
        f"<b>Price:</b> ${campaign.price}\n\n"
        "Your campaign is now available for channel owners to accept.\n"
        "You'll be notified when someone accepts it!",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await state.clear()
    await callback_query.answer("Campaign created!")


@router.callback_query(F.data == "cancel_campaign", StateFilter(CampaignStates.waiting_for_confirmation))
async def cancel_campaign_creation(callback_query: CallbackQuery, state: FSMContext):
    """Cancel campaign creation."""
    try:
        keyboard = get_main_menu_keyboard(UserRole.ADVERTISER)
        await callback_query.message.edit_text(
            "Campaign creation cancelled.\n\n"
            "What would you like to do?",
            reply_markup=keyboard
        )
        await state.clear()
        await callback_query.answer("Campaign cancelled")
        
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "campaign cancellation", state)