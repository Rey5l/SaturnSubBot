"""Middleware: блокировка доступа к боту до подписки на обязательные каналы."""
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

import config
from database import get_mandatory_channels
from services.mandatory_subscription import (
    check_mandatory_subscription,
    build_subscription_keyboard,
    SUBSCRIPTION_MESSAGE,
    MANDATORY_CHECK_CALLBACK,
)


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """Проверяет подписку на обязательные каналы; при отсутствии подписки блокирует доступ."""

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)
        channels = await get_mandatory_channels()
        if not channels:
            return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data == MANDATORY_CHECK_CALLBACK:
            return await handler(event, data)

        bot = data.get("bot")
        if not bot:
            return await handler(event, data)

        ok, not_subbed = await check_mandatory_subscription(bot, user_id)
        if ok:
            return await handler(event, data)

        keyboard = build_subscription_keyboard(not_subbed if not_subbed else channels)
        if isinstance(event, Message):
            await event.answer(
                SUBSCRIPTION_MESSAGE,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            return
        if isinstance(event, CallbackQuery):
            try:
                await event.message.edit_text(
                    SUBSCRIPTION_MESSAGE,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
            except Exception:
                await event.message.answer(
                    SUBSCRIPTION_MESSAGE,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
            await event.answer()
            return
        return await handler(event, data)
