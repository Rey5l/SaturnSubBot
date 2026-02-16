"""Flyer и Tgrass — интеграция по документации: check, offers/tasks, кнопка «Проверить подписку»."""
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import config
from handlers.menu import BTN_FLY, BTN_GRS
from database import (
    flyer_save_pending,
    flyer_get_pending_by_id,
    flyer_get_pending_by_user,
    flyer_already_completed,
    flyer_mark_completed_and_freeze,
    grs_set_pending_credit,
    grs_take_pending_amount,
    grs_clear_pending_credit,
    frozen_add,
)
from services.flyer_api import flyer_check as flyer_check_api, get_tasks as flyer_get_tasks, check_task as flyer_check_task
from services.tgrassa_api import tgrass_check

router = Router(name="platforms")

ALERT_MAX_LEN = 200


def _alert(text: str) -> str:
    if len(text) <= ALERT_MAX_LEN:
        return text
    return text[: ALERT_MAX_LEN - 3] + "..."

TASK_LABELS = {
    "start bot": "Бот",
    "subscribe channel": "Подписка на канал",
    "give boost": "Буст",
    "follow link": "Перейти по ссылке",
    "perform action": "Действие",
    "view posts": "Просмотр постов",
}


def _user_lang(user) -> str:
    return (user.language_code or "ru") if user else "ru"


def _format_earn_usd(amount: float) -> str:
    """Форматирование суммы в долларах (например 0.008$)."""
    if amount >= 1:
        return f"{amount:.2f}$"
    s = f"{amount:.4f}".rstrip("0").rstrip(".")
    return s + "$" if s else "0$"


def _format_earn_cents(amount_usd: float) -> str:
    """Сумма, которую пользователь получит, в центах (учёт PAYOUT_RATE уже в amount_usd)."""
    cents = round(amount_usd * 100)
    return f"{cents} ¢"


def _parse_price_usd(item: dict) -> float:
    """Извлечь цену задания в USD из объекта оффера/таска. Пробуем разные поля API."""
    for key in ("price", "reward", "amount", "pay", "reward_amount", "cost", "price_usd", "reward_cents"):
        val = item.get(key)
        if val is None:
            continue
        try:
            n = float(val)
        except (TypeError, ValueError):
            continue
        if n < 0:
            continue
        if "cents" in key.lower():
            n = n / 100.0
        return n
    return 0.0


def _user_premium(user) -> bool:
    return getattr(user, "is_premium", False) or False


# --- Tgrass: tgrass.space/offers, status ok | no_offers | not_ok, offers[] ---

GRS_TASKS_LIMIT = 5  # сколько заданий Grs показывать

async def _build_tgrassa_content(
    user_id: int, username: str, user, data: dict | None = None
) -> tuple[str, list]:
    """Собирает текст и инлайн-кнопки для блока Grs задания. data — уже полученный ответ API (если есть)."""
    if not config.TGRASSA_API_KEY:
        text = "🌿 *Grs задания*\n\nAPI-ключ не настроен. Перейдите в @tgrassbot."
        return text, [[InlineKeyboardButton(text="Открыть @tgrassbot", url=config.get_tgrassa_link())]]

    if data is None:
        try:
            data = await tgrass_check(
                key=config.TGRASSA_API_KEY,
                tg_user_id=user_id,
                tg_login=username,
                lang=_user_lang(user),
                is_premium=_user_premium(user),
            )
        except Exception as e:
            err_str = str(e).lower()
            if "ssl" in err_str or "certificate" in err_str:
                msg = "Ошибка SSL. Добавьте в .env: TGRASSA_API_SSL_VERIFY=false"
            else:
                msg = str(e).split("\n")[0].strip()
            return f"🌿 *Grs задания*\n\n❌ Ошибка API: {msg[:200]}", []

    status = (data.get("status") or "").lower().strip()
    if status in ("ok", "no_offers"):
        await grs_clear_pending_credit(user_id)
        text = "🌿 *Grs задания*\n\n📝 Доступных заданий: 0\n───────────────\n💫 Можно заработать: 0 ¢\n\n✅ Проверка пройдена или заданий нет."
        return text, []

    offers_raw = data.get("offers") or []
    if status != "not_ok":
        # Неизвестный status (пустой, error и т.д.) — не затираем экран, показываем офферы если есть
        if offers_raw:
            pass  # показываем офферы ниже
        else:
            text = (
                "🌿 *Grs задания*\n\n"
                "Сервис временно вернул неожиданный ответ. Нажмите «Обновить» или откройте Grs задания снова."
            )
            rows = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:tgrassa")]]
            return text, rows

    offers = offers_raw[:GRS_TASKS_LIMIT]
    if not offers:
        text = "🌿 *Grs задания*\n\n📝 Доступных заданий: 0\n───────────────\n💫 Можно заработать: 0 ¢"
        return text, []
    n = len(offers)
    rate = config.TGRASSA_PAYOUT_RATE
    total_payout = 0.0
    for o in offers:
        api_price = _parse_price_usd(o)
        total_payout += api_price * rate
    earn_str = _format_earn_cents(total_payout)
    text = (
        f"🌿 *Grs задания*\n\n"
        f"📝 Доступных заданий: {n}\n"
        f"───────────────\n"
        f"💫 Можно заработать: {earn_str}"
    )
    rows = []
    for o in offers:
        name = (o.get("name") or o.get("title") or "Канал").strip() or "Канал"
        link = o.get("link") or o.get("url") or ""
        if link:
            rows.append([InlineKeyboardButton(text=f"📢 {name[:30]}", url=link)])
    rows.append([InlineKeyboardButton(text="Проверить подписку 🔄", callback_data="check_tgrass")])
    if total_payout > 0:
        await grs_set_pending_credit(user_id, total_payout)
    return text, rows


@router.callback_query(F.data == "platform:tgrassa")
async def show_tgrassa(callback: CallbackQuery) -> None:
    """Grs задания по callback."""
    user = callback.from_user
    user_id = user.id if user else 0
    username = (user.username or "") if user else ""
    text, rows = await _build_tgrassa_content(user_id, username, user)
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(F.text == BTN_GRS)
async def show_tgrassa_message(message: Message) -> None:
    """Grs задания по нажатию кнопки нижнего меню."""
    user = message.from_user
    user_id = user.id if user else 0
    username = (user.username or "") if user else ""
    text, rows = await _build_tgrassa_content(user_id, username, user)
    if rows:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "check_tgrass")
async def callback_check_tgrass(callback: CallbackQuery) -> None:
    """Повторная проверка Tgrass: снова POST /offers. Если ok/no_offers — успех."""
    user = callback.from_user
    user_id = user.id if user else 0
    username = (user.username or "") if user else ""
    if not config.TGRASSA_API_KEY:
        await callback.answer("API не настроен.", show_alert=True)
        return

    try:
        data = await tgrass_check(
            key=config.TGRASSA_API_KEY,
            tg_user_id=user_id,
            tg_login=username,
            lang=_user_lang(user),
            is_premium=_user_premium(user),
        )
    except Exception as e:
        err_msg = str(e).split("\n")[0].strip()
        await callback.answer(_alert(f"Ошибка: {err_msg}"), show_alert=True)
        return

    status = (data.get("status") or "").lower().strip()
    if status in ("ok", "no_offers"):
        amount = await grs_take_pending_amount(user_id)
        if amount > 0:
            unfreeze_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            await frozen_add(user_id, amount, unfreeze_at, "grs")
            await callback.answer(
                f"✅ Проверка пройдена! Сумма {amount:.2f} заморожена на 24 ч. Если останетесь подписанным — будет зачислена на баланс.",
                show_alert=True,
            )
        else:
            await callback.answer("✅ Проверка пройдена!", show_alert=True)
        await show_tgrassa(callback)
        return

    # Подписки ещё не выполнены — перерисовываем экран из того же ответа API (без повторного запроса)
    await callback.answer("Подпишитесь на все каналы выше и нажмите «Проверить подписку» снова.", show_alert=True)
    text, rows = await _build_tgrassa_content(user_id, username, user, data=data)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
            parse_mode="Markdown",
        )
    except Exception:
        pass


# --- Flyer: единый формат заданий (Доступных заданий / Можно заработать $) ---


async def _build_flyer_content(user_id: int, lang: str) -> tuple[str, list]:
    """
    Собирает текст и инлайн-кнопки для блока Fly задания.
    Возвращает (text, rows). При ошибке или отсутствии заданий — тоже (text, rows).
    """
    if not config.FLYER_API_KEY:
        text = "✈ *Fly задания*\n\nAPI-ключ не настроен. Перейдите в @FlyerServiceBot."
        rows = [[InlineKeyboardButton(text="Открыть @FlyerServiceBot", url=config.get_flyer_link())]]
        return text, rows

    # Не вызываем flyer_check: он приводит к отдельному сообщению от сервиса
    # «Чтобы получить доступ к функциям бота, необходимо выполнить все действия».
    try:
        data = await flyer_get_tasks(
            key=config.FLYER_API_KEY,
            user_id=user_id,
            limit=5,
            language_code=lang,
        )
    except Exception as e:
        return f"✈ *Fly задания*\n\n❌ Ошибка API: {str(e).split(chr(10))[0][:200]}", []

    error = data.get("error")
    if error:
        err_lower = error.lower()
        if "prohibited method" in err_lower or "bot type" in err_lower:
            text = "✈ *Fly задания*\n\nИспользуется ключ для рекламодателя. Нужен ключ бота-исполнителя в @FlyerServiceBot."
        else:
            text = f"✈ *Fly задания*\n\n❌ {error[:400]}"
        rows = [[InlineKeyboardButton(text="Открыть @FlyerServiceBot", url=config.get_flyer_link())]]
        return text, rows

    result = data.get("result") or data.get("tasks") or []
    if isinstance(result, dict):
        result = result.get("tasks") or result.get("list") or []
    if not result:
        text = "✈ *Fly задания*\n\n📝 Доступных заданий: 0\n───────────────\n💫 Можно заработать: 0 ¢"
        rows = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:flyer")]]
        return text, rows

    rate = config.FLYER_PAYOUT_RATE
    total_payout = sum(_parse_price_usd(t) for t in result) * rate
    n = len(result)
    earn_str = _format_earn_cents(total_payout)
    header = (
        f"✈ *Fly задания*\n\n"
        f"📝 Доступных заданий: {n}\n"
        f"───────────────\n"
        f"💫 Можно заработать: {earn_str}"
    )
    rows = []
    for t in result:
        signature = t.get("signature") or ""
        name = (t.get("name") or t.get("task") or "Задание").strip() or "Задание"
        price = _parse_price_usd(t)
        links = t.get("links") or []
        link_url = t.get("link")
        if not link_url and links:
            first = links[0]
            link_url = first if isinstance(first, str) else (first.get("url") or first.get("link") if isinstance(first, dict) else None)
        pending_id = await flyer_save_pending(user_id, signature, price)
        if link_url:
            rows.append([InlineKeyboardButton(text=f"📢 {name[:28]}", url=str(link_url))])
        rows.append([InlineKeyboardButton(text="✅ Проверить", callback_data=f"checkfly:{pending_id}")])
    rows.append([InlineKeyboardButton(text="Проверить подписку 🔄", callback_data="flyer_check")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:flyer")])
    return header, rows


@router.callback_query(F.data == "platform:flyer")
async def show_flyer(callback: CallbackQuery) -> None:
    """Fly задания по callback (кнопка из инлайн-меню или Обновить)."""
    user_id = callback.from_user.id if callback.from_user else 0
    lang = _user_lang(callback.from_user)
    text, rows = await _build_flyer_content(user_id, lang)
    if rows:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="Markdown",
        )
    else:
        await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


@router.message(F.text == BTN_FLY)
async def show_flyer_message(message: Message) -> None:
    """Fly задания по нажатию кнопки нижнего меню."""
    user_id = message.from_user.id if message.from_user else 0
    lang = _user_lang(message.from_user)
    text, rows = await _build_flyer_content(user_id, lang)
    if rows:
        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="Markdown",
        )
    else:
        await message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "flyer_check")
async def callback_flyer_check(callback: CallbackQuery) -> None:
    """Повторная проверка Flyer: /check. Если skip — успех, иначе снова показываем задания."""
    user_id = callback.from_user.id if callback.from_user else 0
    lang = _user_lang(callback.from_user)
    if not config.FLYER_API_KEY:
        await callback.answer("API не настроен.", show_alert=True)
        return

    try:
        check_data = await flyer_check_api(
            key=config.FLYER_API_KEY,
            user_id=user_id,
            language_code=lang,
        )
    except Exception as e:
        err_msg = str(e).split("\n")[0].strip()
        await callback.answer(_alert(f"Ошибка: {err_msg}"), show_alert=True)
        return

    if check_data.get("skip") is True:
        # Проверяем все pending-задания Flyer и замораживаем выплату на 24 ч за выполненные
        pending_list = await flyer_get_pending_by_user(user_id)
        unfreeze_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        total_frozen = 0.0
        for p in pending_list:
            sig = p["signature"]
            if await flyer_already_completed(user_id, sig):
                continue
            try:
                task_data = await flyer_check_task(
                    key=config.FLYER_API_KEY, user_id=user_id, signature=sig
                )
            except Exception:
                continue
            if task_data.get("result") == "complete":
                payout = float(p["price"]) * config.FLYER_PAYOUT_RATE
                await flyer_mark_completed_and_freeze(user_id, sig, payout, unfreeze_at)
                total_frozen += payout
        if total_frozen > 0:
            await callback.answer(
                f"✅ Проверка пройдена! Сумма {total_frozen:.2f} заморожена на 24 ч. Если останетесь подписанным — будет зачислена на баланс.",
                show_alert=True,
            )
        else:
            await callback.answer("✅ Проверка пройдена!", show_alert=True)
        await show_flyer(callback)
        return

    await callback.answer("Выполните задания и нажмите «Проверить подписку» снова.", show_alert=True)
    await show_flyer(callback)


@router.callback_query(F.data.startswith("checkfly:"))
async def check_flyer_task(callback: CallbackQuery) -> None:
    """Проверить одно задание Flyer (check_task) и зачислить награду."""
    try:
        pending_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка запроса.", show_alert=True)
        return

    pending = await flyer_get_pending_by_id(pending_id)
    if not pending:
        await callback.answer("Задание не найдено или уже проверено.", show_alert=True)
        return

    user_id = callback.from_user.id if callback.from_user else 0
    if pending["user_id"] != user_id:
        await callback.answer("Это не ваше задание.", show_alert=True)
        return

    signature = pending["signature"]
    price = float(pending["price"])

    if await flyer_already_completed(user_id, signature):
        await callback.answer("Вы уже получали награду за это задание.", show_alert=True)
        return

    if not config.FLYER_API_KEY:
        await callback.answer("API Flyer не настроен.", show_alert=True)
        return

    try:
        data = await flyer_check_task(key=config.FLYER_API_KEY, user_id=user_id, signature=signature)
    except Exception as e:
        err_msg = str(e).split("\n")[0].strip()
        await callback.answer(_alert(f"Ошибка проверки: {err_msg}"), show_alert=True)
        return

    result = data.get("result")
    error = data.get("error")
    if error:
        await callback.answer(_alert(f"Ошибка: {error}"), show_alert=True)
        return

    if result == "complete":
        payout = price * config.FLYER_PAYOUT_RATE
        unfreeze_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        await flyer_mark_completed_and_freeze(user_id, signature, payout, unfreeze_at)
        await callback.answer(
            f"✅ Сумма {payout:.2f} заморожена на 24 ч. Если останетесь подписанным — будет зачислена на баланс.",
            show_alert=True,
        )
        await show_flyer(callback)
        return

    if result == "waiting":
        await callback.answer("Задание принято, награда в течение 24 часов.", show_alert=True)
        return

    if result == "incomplete":
        await callback.answer("Задание ещё не выполнено. Выполните и нажмите «Проверить» снова.", show_alert=True)
        return

    if result == "abort":
        await callback.answer("Подписка отменена. Подпишитесь снова и нажмите «Проверить».", show_alert=True)
        return

    if result == "unavailable":
        await callback.answer("Задание недоступно.", show_alert=True)
        return

    await callback.answer(_alert(f"Статус: {result}. Попробуйте позже."), show_alert=True)
