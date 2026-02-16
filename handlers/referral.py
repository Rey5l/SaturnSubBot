"""Реферальная система."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import config
from database import count_referrals
from handlers.menu import BTN_REFERRAL

router = Router(name="referral")

REFERRAL_BONUS_PERCENT = int(config.REFERRAL_BONUS_RATE * 100)


def back_button() -> list:
    return [[InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")]]


def _referral_link(user_id: int) -> str:
    """Ссылка для приглашения."""
    base = f"https://t.me/{config.BOT_USERNAME}" if config.BOT_USERNAME else "https://t.me/your_bot"
    return f"{base}?start=ref_{user_id}"


def _referral_text(count: int, link: str) -> str:
    return (
        "🎯 *Реферальная система*\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👥 Ваших рефералов: *{count}*\n"
        "────────────────\n"
        "🎁 *Бонусы:*\n"
        f"╰• Вы получаете {REFERRAL_BONUS_PERCENT}% от их выводов\n"
        "────────────────\n"
        "🔗 *Ссылка для приглашения:*\n\n"
        f"`{link}`"
    )


@router.callback_query(F.data == "referral")
async def show_referral(callback: CallbackQuery) -> None:
    """Блок реферальной системы по callback."""
    user_id = callback.from_user.id if callback.from_user else 0
    count = await count_referrals(user_id)
    link = _referral_link(user_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Копировать ссылку", url=f"https://t.me/share/url?url={link}")],
            *back_button(),
        ]
    )
    await callback.message.edit_text(_referral_text(count, link), reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.message(F.text == BTN_REFERRAL)
async def show_referral_message(message: Message) -> None:
    """Реферальная система по кнопке нижнего меню."""
    user_id = message.from_user.id if message.from_user else 0
    count = await count_referrals(user_id)
    link = _referral_link(user_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Копировать ссылку", url=f"https://t.me/share/url?url={link}")]]
    )
    await message.answer(_referral_text(count, link), reply_markup=keyboard, parse_mode="Markdown")
