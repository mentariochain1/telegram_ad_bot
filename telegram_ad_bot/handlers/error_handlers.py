"""Centralized error handling for bot handlers."""

from typing import Union
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext

from telegram_ad_bot.services.user_service import UserServiceError, UserNotFoundError
from telegram_ad_bot.services.channel_service import ChannelServiceError, InvalidOwnerError, ChannelAlreadyExistsError
from telegram_ad_bot.services.campaign_service import CampaignServiceError, CampaignValidationError, InsufficientBalanceError
from telegram_ad_bot.config.logging import get_logger

logger = get_logger(__name__)


async def handle_user_service_error(
    update: Union[Message, CallbackQuery], 
    error: UserServiceError,
    context: str = "operation"
) -> None:
    """Handle user service errors with appropriate user feedback."""
    logger.error(f"User service error in {context}: {error}")
    
    if isinstance(error, UserNotFoundError):
        message = "User not found. Please start over with /start"
    else:
        message = f"User {context} failed. Please try again later."
    
    if isinstance(update, CallbackQuery):
        await update.answer(message, show_alert=True)
    else:
        await update.answer(message)


async def handle_channel_service_error(
    update: Union[Message, CallbackQuery],
    error: ChannelServiceError,
    context: str = "operation"
) -> None:
    """Handle channel service errors with appropriate user feedback."""
    logger.error(f"Channel service error in {context}: {error}")
    
    if isinstance(error, (ChannelAlreadyExistsError, InvalidOwnerError)):
        message = f"Channel {context} failed: {str(error)}"
    else:
        message = f"Channel {context} failed. Please try again later."
    
    if isinstance(update, CallbackQuery):
        await update.answer(message, show_alert=True)
    else:
        await update.answer(message)


async def handle_campaign_service_error(
    update: Union[Message, CallbackQuery],
    error: CampaignServiceError,
    context: str = "operation"
) -> None:
    """Handle campaign service errors with appropriate user feedback."""
    logger.error(f"Campaign service error in {context}: {error}")
    
    if isinstance(error, (CampaignValidationError, InsufficientBalanceError)):
        message = f"Campaign {context} failed: {str(error)}"
    else:
        message = f"Campaign {context} failed. Please try again later."
    
    if isinstance(update, CallbackQuery):
        await update.answer(message, show_alert=True)
    else:
        await update.answer(message)


async def handle_telegram_api_error(
    update: Union[Message, CallbackQuery],
    error: TelegramAPIError,
    context: str = "operation"
) -> None:
    """Handle Telegram API errors with appropriate user feedback."""
    logger.error(f"Telegram API error in {context}: {error}")
    
    message = "Communication error. Please try again."
    
    if isinstance(update, CallbackQuery):
        await update.answer(message, show_alert=True)
    else:
        await update.answer(message)


async def handle_unexpected_error(
    update: Union[Message, CallbackQuery],
    error: Exception,
    context: str = "operation",
    state: FSMContext = None
) -> None:
    """Handle unexpected errors with cleanup."""
    logger.error(f"Unexpected error in {context}: {error}")
    
    if state:
        await state.clear()
    
    message = "An unexpected error occurred. Please try again."
    
    if isinstance(update, CallbackQuery):
        await update.answer(message, show_alert=True)
    else:
        await update.answer(message)


async def safe_state_clear(state: FSMContext, context: str = "operation") -> None:
    """Safely clear state with error logging."""
    try:
        await state.clear()
    except Exception as e:
        logger.error(f"Error clearing state in {context}: {e}")