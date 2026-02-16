"""Админ: зачисление баланса, добавление каналов для заданий."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import add_balance, get_balance, add_channel_task, get_channel_tasks

router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class AddBalanceStates(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


class AddChannelStates(StatesGroup):
    waiting_platform = State()
    waiting_channel = State()
    waiting_reward = State()
    waiting_title = State()


@router.message(Command("addbalance"))
async def cmd_add_balance(message: Message, state: FSMContext) -> None:
    """Команда /addbalance — только для админов."""
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    await state.set_state(AddBalanceStates.waiting_user_id)
    await message.answer("Введите user_id пользователя (число):")


@router.message(AddBalanceStates.waiting_user_id, F.text)
async def admin_user_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите число (Telegram user_id).")
        return
    await state.update_data(target_user_id=user_id)
    await state.set_state(AddBalanceStates.waiting_amount)
    await message.answer("Введите сумму для зачисления:")


@router.message(AddBalanceStates.waiting_amount, F.text)
async def admin_amount(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введите число (сумма).")
        return
    if amount <= 0:
        await message.answer("Сумма должна быть больше 0.")
        return
    data = await state.get_data()
    target_user_id = data["target_user_id"]
    await state.clear()
    try:
        new_balance = await add_balance(target_user_id, amount)
        await message.answer(f"✅ Зачислено {amount} пользователю {target_user_id}. Новый баланс: {new_balance:.2f}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("balance_admin"))
async def cmd_balance_admin(message: Message) -> None:
    """Проверить баланс пользователя по user_id. Использование: /balance_admin 123456789"""
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Использование: /balance_admin <user_id>")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer("user_id должен быть числом.")
        return
    balance = await get_balance(user_id)
    await message.answer(f"Баланс user_id={user_id}: {balance:.2f}")


# --- Добавление каналов для заданий ---

@router.message(Command("addchannel"))
async def cmd_add_channel(message: Message, state: FSMContext) -> None:
    """Добавить канал для заданий (подписка). Только админ."""
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌿 Grs (Tgrassa)", callback_data="addch_platform:tgrassa"),
                InlineKeyboardButton(text="✈ Fly (Flyer)", callback_data="addch_platform:flyer"),
            ],
        ]
    )
    await state.set_state(AddChannelStates.waiting_platform)
    await message.answer("Выберите платформу для задания:", reply_markup=kb)


@router.callback_query(F.data.startswith("addch_platform:"), AddChannelStates.waiting_platform)
async def add_channel_platform(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id if callback.from_user else 0):
        return
    platform = callback.data.split(":")[1]
    await state.update_data(platform=platform)
    await state.set_state(AddChannelStates.waiting_channel)
    await callback.message.edit_text(
        f"Платформа: {platform}\n\nВведите username канала (например @channelname или channelname):"
    )
    await callback.answer()


@router.message(AddChannelStates.waiting_channel, F.text)
async def add_channel_username(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    username = message.text.strip().lstrip("@")
    if not username or " " in username:
        await message.answer("Введите один username без пробелов (например channelname или @channelname).")
        return
    await state.update_data(channel_username=username)
    await state.set_state(AddChannelStates.waiting_reward)
    await message.answer("Введите награду за подписку (число, например 0.5 или 1):")


@router.message(AddChannelStates.waiting_reward, F.text)
async def add_channel_reward(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    try:
        reward = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введите число (награда).")
        return
    if reward <= 0:
        await message.answer("Награда должна быть больше 0.")
        return
    await state.update_data(reward=reward)
    await state.set_state(AddChannelStates.waiting_title)
    await message.answer(
        "Введите название задания (или /skip чтобы оставить username канала):"
    )


@router.message(AddChannelStates.waiting_title, F.text)
async def add_channel_title(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    title = message.text.strip() if message.text and message.text.strip() != "/skip" else ""
    data = await state.get_data()
    await state.clear()
    try:
        task_id = await add_channel_task(
            channel_username=data["channel_username"],
            reward=data["reward"],
            platform=data["platform"],
            title=title or None,
        )
        await message.answer(
            f"✅ Задание добавлено (id={task_id}).\n"
            f"Канал: @{data['channel_username']}\n"
            f"Награда: {data['reward']}\n"
            f"Платформа: {data['platform']}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("channels"))
async def cmd_list_channels(message: Message) -> None:
    """Список добавленных каналов-заданий. Только админ."""
    if not is_admin(message.from_user.id if message.from_user else 0):
        return
    for platform, label in [("tgrassa", "Grs"), ("flyer", "Fly")]:
        tasks = await get_channel_tasks(platform=platform, active_only=False)
        if not tasks:
            await message.answer(f"**{label}:** заданий нет.")
            continue
        lines = [f"**{label}:**"]
        for t in tasks:
            status = "✅" if t["is_active"] else "⏸"
            lines.append(f"{status} id={t['id']} @{t['channel_username']} +{t['reward']:.2f}")
        await message.answer("\n".join(lines))
