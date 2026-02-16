"""Вывод средств в Crypto Bot."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import get_balance, get_referrer_id, add_balance
from services.crypto_pay import transfer_to_user
from handlers.menu import BTN_WITHDRAW, main_reply_keyboard

router = Router(name="withdraw")


class WithdrawStates(StatesGroup):
    entering_amount = State()


def back_button() -> list:
    return [[InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_menu")]]


async def _start_withdraw_common(user_id: int) -> tuple[str | None, list | None]:
    """
    Общая логика начала вывода. Возвращает (text, rows) или (error_text, error_rows).
    Если всё ок для ввода суммы — возвращает (prompt_text, back_button()).
    """
    if not config.CRYPTO_PAY_ENABLED:
        return "Вывод через Crypto Bot не настроен. Обратитесь к администратору.", back_button()

    balance = await get_balance(user_id)
    asset = config.WITHDRAW_ASSET
    min_sum = config.MIN_WITHDRAW_AMOUNT

    if balance < min_sum:
        return (
            f"💰 Ваш баланс: {balance:.2f}\n\n"
            f"Минимальная сумма вывода: {min_sum} {asset}.\n"
            "Выполняйте задания в Fly и Grs, после зачисления можно вывести средства.",
            back_button(),
        )

    prompt = (
        f"💸 **Вывод в Crypto Bot**\n\n"
        f"Ваш баланс: **{balance:.2f}**\n"
        f"Минимум: **{min_sum}** {asset}\n\n"
        f"Введите сумму для вывода (число, например 5 или 10.5):"
    )
    return prompt, back_button()


@router.callback_query(F.data == "withdraw")
async def start_withdraw(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало процесса вывода по callback."""
    user_id = callback.from_user.id if callback.from_user else 0
    text, rows = await _start_withdraw_common(user_id)
    if text and "Введите сумму" in text:
        await state.set_state(WithdrawStates.entering_amount)
        await state.update_data(asset=config.WITHDRAW_ASSET)
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(F.text == BTN_WITHDRAW)
async def start_withdraw_message(message: Message, state: FSMContext) -> None:
    """Начало процесса вывода по кнопке нижнего меню."""
    user_id = message.from_user.id if message.from_user else 0
    text, rows = await _start_withdraw_common(user_id)
    if text and "Введите сумму" in text:
        await state.set_state(WithdrawStates.entering_amount)
        await state.update_data(asset=config.WITHDRAW_ASSET)
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="Markdown",
    )


@router.message(WithdrawStates.entering_amount, F.text)
async def process_withdraw_amount(message: Message, state: FSMContext) -> None:
    """Обработка введённой суммы и выполнение вывода."""
    text = message.text.strip().replace(",", ".")
    try:
        amount = float(text)
    except ValueError:
        await message.answer("Введите число (например 5 или 10.5).")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше нуля.")
        return

    user_id = message.from_user.id if message.from_user else 0
    data = await state.get_data()
    asset = data.get("asset", config.WITHDRAW_ASSET)
    await state.clear()

    ok, msg = await transfer_to_user(
        user_id=user_id,
        amount=amount,
        asset=asset,
        comment="Saturn",
        deduct_user_balance=True,
    )

    if ok:
        referrer_id = await get_referrer_id(user_id)
        if referrer_id and config.REFERRAL_BONUS_RATE > 0:
            bonus = round(amount * config.REFERRAL_BONUS_RATE, 2)
            await add_balance(referrer_id, bonus)
        await message.answer(f"✅ {msg}")
    else:
        await message.answer(f"❌ {msg}")

    await message.answer("Выберите действие в меню ниже:", reply_markup=main_reply_keyboard())
