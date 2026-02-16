"""Просмотр баланса пользователя."""
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import get_balance, frozen_get_summary
from handlers.menu import BTN_CABINET

router = Router(name="balance")


def back_button() -> list:
    return [[InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")]]


def _format_unfreeze_at(dt_str: str | None) -> str:
    """Форматирование даты разморозки для отображения."""
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return dt_str


async def _balance_text(balance: float, user_id: int) -> str:
    frozen_total, min_unfreeze = await frozen_get_summary(user_id)
    lines = [
        "💻 *Личный кабинет*",
        "━━━━━━━━━━━━━━━━━",
        f"💰 Ваш баланс: *{balance:.2f}*",
    ]
    if frozen_total > 0:
        lines.append(f"❄️ Заморожено: *{frozen_total:.2f}*")
        if min_unfreeze:
            lines.append(f"   _Разморозка: {_format_unfreeze_at(min_unfreeze)}_")
    lines.append("")
    lines.append("Баланс можно вывести в Crypto Bot (кнопка «Вывод»).")
    lines.append("Замороженные средства зачислятся через 24 ч, если вы останетесь подписанным.")
    return "\n".join(lines)


@router.callback_query(F.data == "balance")
async def show_balance(callback: CallbackQuery) -> None:
    """Показать личный кабинет по callback."""
    user_id = callback.from_user.id if callback.from_user else 0
    balance = await get_balance(user_id)
    text = await _balance_text(balance, user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=back_button())
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.message(F.text == BTN_CABINET)
async def show_balance_message(message: Message) -> None:
    """Показать личный кабинет по кнопке нижнего меню."""
    user_id = message.from_user.id if message.from_user else 0
    balance = await get_balance(user_id)
    text = await _balance_text(balance, user_id)
    await message.answer(text, parse_mode="Markdown")
