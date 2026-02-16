"""Главное меню и навигация."""
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

import config

router = Router(name="menu")

# Тексты кнопок нижнего меню (используются в обработчиках по F.text)
BTN_FLY = "✈ Fly задания"
BTN_GRS = "🌿 Grs задания"
BTN_CABINET = "💻 Кабинет"
BTN_REFERRAL = "👤 Рефералы"
BTN_STATS = "📂 Статистика"
BTN_WITHDRAW = "💸 Вывод"

WELCOME_TEXT = """👋 Добро пожаловать!

✅ *Доступные задания:*
├ ✈ Fly задания
├ 🌿 Grs задания

💎 *Возможности бота:*
├ 💻 Личный кабинет
├ 👤 Реферальная система
├ 📂 Статистика и информация
╰ 💸 Быстрый вывод средств

🚀 Начните зарабатывать прямо сейчас!

🚀 Saturn — бот для заработка на подписках и заданиях, с самой высокой оплатой в ТГ!"""


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Нижнее постоянное меню (Reply Keyboard)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FLY), KeyboardButton(text=BTN_GRS)],
            [KeyboardButton(text=BTN_CABINET), KeyboardButton(text=BTN_REFERRAL)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_WITHDRAW)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_keyboard() -> InlineKeyboardMarkup:
    """Инлайн-клавиатура главного меню (для совместимости callback)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✈ Fly задания", callback_data="platform:flyer"),
                InlineKeyboardButton(text="🌿 Grs задания", callback_data="platform:tgrassa"),
            ],
            [
                InlineKeyboardButton(text="💻 Личный кабинет", callback_data="balance"),
                InlineKeyboardButton(text="👤 Реферальная система", callback_data="referral"),
            ],
            [
                InlineKeyboardButton(text="📂 Статистика и информация", callback_data="info"),
                InlineKeyboardButton(text="💸 Вывод средств", callback_data="withdraw"),
            ],
        ]
    )


def _parse_start_referrer(text: str) -> int | None:
    """Из /start ref_12345 извлечь referrer_id 12345."""
    if not text:
        return None
    args = text.strip().split()
    if len(args) < 2:
        return None
    payload = args[1]  # после /start
    if payload.lower().startswith("ref_"):
        try:
            return int(payload[4:])
        except ValueError:
            pass
    return None


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Команда /start. Поддержка реферальной ссылки: /start ref_12345."""
    from database import get_or_create_user

    user_id = message.from_user.id if message.from_user else 0
    username = message.from_user.username if message.from_user else None
    referrer_id = _parse_start_referrer(message.text or "")
    if referrer_id is not None and referrer_id == user_id:
        referrer_id = None  # не приглашать самого себя
    await get_or_create_user(user_id, username, referrer_id)
    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_reply_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат в главное меню (убираем инлайн, остаётся нижнее меню)."""
    await state.clear()
    await callback.message.edit_text(
        "Выберите действие в меню ниже:",
        reply_markup=None,
    )
    await callback.answer()
