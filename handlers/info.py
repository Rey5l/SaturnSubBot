"""Статистика и информация о боте."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    stats_total_users,
    stats_users_today,
    stats_tasks_completed,
    stats_tasks_completed_channels,
    stats_withdrawn_total,
    stats_withdrawn_today,
)
from handlers.menu import BTN_STATS

router = Router(name="info")


def back_button() -> list:
    return [[InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")]]


async def _info_text() -> str:
    total_users = await stats_total_users()
    users_today = await stats_users_today()
    tasks_done = await stats_tasks_completed() + await stats_tasks_completed_channels()
    withdrawn_total = await stats_withdrawn_total()
    withdrawn_today = await stats_withdrawn_today()
    return (
        "📚 *Информация о нашем боте:*\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"👥 Пользователей всего: *{total_users}*\n"
        f"╰• За сегодня: *{users_today}*\n"
        "────────────────\n"
        f"📝 Выполнено заданий: *{tasks_done}*\n"
        "────────────────\n"
        f"💸 Выведено всего: *{withdrawn_total:.2f}* USD\n"
        f"╰• За сегодня: *{withdrawn_today:.2f}* USD\n"
        "────────────────\n"
        "📈 Статистика обновляется в реальном времени."
    )


@router.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery) -> None:
    """Блок информации по callback."""
    text = await _info_text()
    keyboard = InlineKeyboardMarkup(inline_keyboard=back_button())
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()


@router.message(F.text == BTN_STATS)
async def show_info_message(message: Message) -> None:
    """Статистика по кнопке нижнего меню."""
    text = await _info_text()
    await message.answer(text, parse_mode="Markdown")
