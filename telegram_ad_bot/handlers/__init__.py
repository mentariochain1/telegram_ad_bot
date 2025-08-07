"""Handlers package with refactored, maintainable bot handlers."""

from telegram_ad_bot.handlers import (
    registration_handlers,
    campaign_handlers, 
    bot_handlers
)

from aiogram import Router

main_router = Router()
main_router.include_router(registration_handlers.router)
main_router.include_router(campaign_handlers.router)
main_router.include_router(bot_handlers.router)

router = main_router

__all__ = [
    'router',
    'registration_handlers',
    'campaign_handlers',
    'bot_handlers'
]