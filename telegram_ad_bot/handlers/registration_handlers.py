"""Registration-related handlers for user and channel setup."""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from telegram_ad_bot.handlers.states import RegistrationStates
from telegram_ad_bot.handlers.helpers import (
    get_role_selection_keyboard, get_main_menu_keyboard,
    extract_channel_info_from_message, verify_user_is_channel_admin,
    check_bot_permissions_in_channel
)
from telegram_ad_bot.handlers.error_handlers import (
    handle_user_service_error, handle_channel_service_error,
    handle_telegram_api_error, handle_unexpected_error, safe_state_clear
)
from telegram_ad_bot.services.user_service import UserService, UserServiceError
from telegram_ad_bot.services.channel_service import ChannelService, ChannelServiceError, InvalidOwnerError, ChannelAlreadyExistsError
from telegram_ad_bot.models.user import UserRole
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)

router = Router()


@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    """Handle /start command - main entry point."""
    try:
        user_service = UserService()
        existing_user = await user_service.get_user_by_telegram_id(message.from_user.id)
        
        if existing_user:
            await _show_returning_user_menu(message, existing_user)
        else:
            await _show_role_selection(message, state)
            
    except UserServiceError as e:
        await handle_user_service_error(message, e, "start command")
    except Exception as e:
        await handle_unexpected_error(message, e, "start command", state)


async def _show_returning_user_menu(message: Message, user):
    """Show main menu for returning users."""
    keyboard = get_main_menu_keyboard(user.role)
    role_text = "Advertiser" if user.role == UserRole.ADVERTISER else "Channel Owner"
    
    await message.answer(
        f"Welcome back! You're registered as a {role_text}.\n\n"
        f"Your current balance: ${user.balance}\n\n"
        "What would you like to do?",
        reply_markup=keyboard
    )


async def _show_role_selection(message: Message, state: FSMContext):
    """Show role selection for new users."""
    keyboard = get_role_selection_keyboard()
    await message.answer(
        "Welcome to AdPost Bot! 🤖\n\n"
        "I help connect advertisers with channel owners for automated ad placements.\n\n"
        "Please select your role to get started:",
        reply_markup=keyboard
    )
    await state.set_state(RegistrationStates.waiting_for_role)


@router.callback_query(F.data.in_(["role_advertiser", "role_channel_owner"]), StateFilter(RegistrationStates.waiting_for_role))
async def handle_role_selection(callback_query: CallbackQuery, state: FSMContext):
    """Handle user role selection during registration."""
    try:
        role = UserRole.ADVERTISER if callback_query.data == "role_advertiser" else UserRole.CHANNEL_OWNER
        
        user_service = UserService()
        await user_service.register_user(
            telegram_id=callback_query.from_user.id,
            username=callback_query.from_user.username,
            role=role
        )
        
        if role == UserRole.ADVERTISER:
            await _complete_advertiser_registration(callback_query, state)
        else:
            await _start_channel_owner_registration(callback_query, state)
            
        await callback_query.answer()
        
    except UserServiceError as e:
        await handle_user_service_error(callback_query, e, "role selection")
    except Exception as e:
        await handle_unexpected_error(callback_query, e, "role selection", state)


async def _complete_advertiser_registration(callback_query: CallbackQuery, state: FSMContext):
    """Complete registration for advertiser role."""
    keyboard = get_main_menu_keyboard(UserRole.ADVERTISER)
    await callback_query.message.edit_text(
        "Great! You're now registered as an Advertiser. 📢\n\n"
        "You can create ad campaigns and they'll be shown to channel owners.\n"
        "Your current balance: $0.00\n\n"
        "What would you like to do?",
        reply_markup=keyboard
    )
    await state.clear()


async def _start_channel_owner_registration(callback_query: CallbackQuery, state: FSMContext):
    """Start channel owner registration process."""
    await callback_query.message.edit_text(
        "Great! You're now registered as a Channel Owner. 📺\n\n"
        "To start receiving ads, I need to verify your channel.\n"
        "Please send me your channel username (e.g., @mychannel) or forward a message from your channel."
    )
    await state.set_state(RegistrationStates.waiting_for_channel_info)


@router.message(StateFilter(RegistrationStates.waiting_for_channel_info))
async def handle_channel_info(message: Message, state: FSMContext):
    """Handle channel information submission."""
    try:
        channel_id, channel_name = await extract_channel_info_from_message(message)
        if not channel_id or not channel_name:
            return
        
        if not await verify_user_is_channel_admin(message, channel_id):
            return
        
        await _register_channel(message, state, channel_id, channel_name)
        
    except Exception as e:
        await handle_unexpected_error(message, e, "channel info", state)


async def _register_channel(message: Message, state: FSMContext, channel_id: str, channel_name: str):
    """Register the channel in the system."""
    user_service = UserService()
    user = await user_service.get_user_by_telegram_id(message.from_user.id)
    
    if not user:
        await message.answer("Registration error. Please start over with /start")
        await safe_state_clear(state, "channel registration")
        return
    
    channel_service = ChannelService()
    try:
        channel = await channel_service.register_channel(
            owner_id=user.id,
            telegram_channel_id=channel_id,
            channel_name=channel_name,
            subscriber_count=0
        )
        
        await state.update_data(channel_id=channel.id)
        await _show_bot_admin_instructions(message, state, channel_name)
        
    except (ChannelAlreadyExistsError, InvalidOwnerError) as e:
        await handle_channel_service_error(message, e, "channel registration")
    except ChannelServiceError as e:
        await handle_channel_service_error(message, e, "channel registration")


async def _show_bot_admin_instructions(message: Message, state: FSMContext, channel_name: str):
    """Show instructions for adding bot as admin."""
    bot_username = (await message.bot.get_me()).username
    await message.answer(
        f"Channel '{channel_name}' registered successfully! ✅\n\n"
        "Now I need to be added as an admin to your channel to post ads.\n\n"
        "Please:\n"
        "1. Go to your channel settings\n"
        "2. Add me (@{bot_username}) as an administrator\n"
        "3. Give me permissions to post messages and pin messages\n"
        "4. Then send me any message to continue"
    )
    await state.set_state(RegistrationStates.waiting_for_channel_verification)


@router.message(StateFilter(RegistrationStates.waiting_for_channel_verification))
async def handle_channel_verification(message: Message, state: FSMContext):
    """Handle channel verification after bot is added as admin."""
    try:
        data = await state.get_data()
        channel_id = data.get("channel_id")
        
        if not channel_id:
            await message.answer("Verification error. Please start over with /start")
            await safe_state_clear(state, "channel verification")
            return
        
        await _verify_bot_permissions(message, state, channel_id)
        
    except Exception as e:
        await handle_unexpected_error(message, e, "channel verification", state)


async def _verify_bot_permissions(message: Message, state: FSMContext, channel_id: int):
    """Verify bot has required permissions in the channel."""
    channel_service = ChannelService()
    channel = await channel_service.get_channel_by_id(channel_id)
    
    if not channel:
        await message.answer("Channel not found. Please start over with /start")
        await safe_state_clear(state, "permission verification")
        return
    
    is_admin, can_post, can_pin = await check_bot_permissions_in_channel(message, channel.telegram_channel_id)
    
    if is_admin and can_post and can_pin:
        await _complete_channel_verification(message, state, channel_service, channel_id)
    elif is_admin:
        await _show_permission_error(message)
    else:
        await _show_admin_error(message)


async def _complete_channel_verification(message: Message, state: FSMContext, channel_service: ChannelService, channel_id: int):
    """Complete the channel verification process."""
    await channel_service.update_bot_admin_status(channel_id, True)
    await channel_service.verify_channel(channel_id, True)
    
    keyboard = get_main_menu_keyboard(UserRole.CHANNEL_OWNER)
    await message.answer(
        "Perfect! Your channel is now verified and ready to receive ads! 🎉\n\n"
        "You can now browse available campaigns and start earning.\n\n"
        "What would you like to do?",
        reply_markup=keyboard
    )
    await state.clear()


async def _show_permission_error(message: Message):
    """Show error message for insufficient permissions."""
    await message.answer(
        "I'm an admin but I need additional permissions:\n"
        "• Post messages\n"
        "• Pin messages\n\n"
        "Please update my permissions and try again."
    )


async def _show_admin_error(message: Message):
    """Show error message when bot is not admin."""
    await message.answer(
        "I'm not an admin of your channel yet.\n"
        "Please add me as an administrator with posting and pinning permissions, then try again."
    )