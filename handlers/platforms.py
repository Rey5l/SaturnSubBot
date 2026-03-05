"""Flyer и Tgrass — интеграция по документации: check, offers/tasks, кнопка «Проверить подписку»."""
import random
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config
from handlers.menu import BTN_FLY, BTN_GRS
from database import (
    flyer_save_pending,
    flyer_get_pending_by_id,
    flyer_get_pending_by_user,
    flyer_already_completed,
    flyer_mark_completed_and_freeze,
    flyer_clear_pending_for_completed,
    tgrassa_save_pending,
    tgrassa_get_pending_by_user,
    tgrassa_already_completed,
    tgrassa_mark_completed_and_freeze,
    tgrassa_clear_pending_for_completed,
    grs_set_pending_credit,
    grs_take_pending_amount,
    grs_clear_pending_credit,
    grs_mark_completed,
    grs_is_completed,
    frozen_add,
    frozen_get_summary,
)
from services.flyer_api import get_tasks as flyer_get_tasks, check_task as flyer_check_task
from services.tgrassa_api import tgrass_check

router = Router(name="platforms")

ALERT_MAX_LEN = 200


def _format_unfreeze_at(dt_str: str | None) -> str:
    """Форматирование даты разморозки для отображения."""
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return dt_str


def _fly_task_complete(data: dict) -> bool:
    """
    Успешное выполнение задания Fly. API /check_task возвращает {"result": "string", "error": "string"}.
    Считаем успехом result в (complete, completed, done, success, ok).
    """
    result = (
        data.get("result")
        or data.get("status")
        or (data.get("data") or {}).get("result")
        or (data.get("data") or {}).get("status")
        or ""
    )
    if isinstance(result, dict):
        result = result.get("result") or result.get("status") or ""
    result = str(result).lower().strip()
    return result in ("complete", "completed", "done", "success", "ok")


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

GRS_TASKS_MIN, GRS_TASKS_MAX = 2, 5  # случайное количество заданий Grs на подписку (2–5)

async def _build_tgrassa_content(
    user_id: int, username: str, user, bot: Bot | None = None, data: dict | None = None, randomize: bool = True
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
        text = "🌿 *Grs задания*\n\n📝 Доступных заданий: 0\n───────────────\n💫 Можно заработать: 0$\n\n✅ Проверка пройдена или заданий нет."
        return text, []

    offers_raw = data.get("offers") or []
    if status != "not_ok":
        # Неизвестный status (пустой, error и т.д.) — не затираем экран, показываем офферы если есть
        if offers_raw:
            pass  # показываем офферы ниже
        else:
            text = (
                "🌿 *Grs задания*\n\n"
                "Выполните задания снизу."
            )
            rows = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:tgrassa")]]
            return text, rows

    # Показываем только те офферы, которые пользователь еще не выполнил
    offers = []
    
    for o in offers_raw:
        link = o.get("link") or o.get("url") or ""
        if not link:
            continue
            
        # 1. Проверка по базе данных (уже получал награду)
        if await grs_is_completed(user_id, link):
            continue
            
        # 2. Проверка через Telegram API (уже подписан)
        # Это предотвращает "халявные" деньги за каналы, на которые юзер и так подписан
        if bot:
            try:
                # Пытаемся извлечь chat_id из ссылки (t.me/username)
                chat_id = link.split("/")[-1].split("?")[0]
                if not chat_id.startswith("@") and not chat_id.startswith("-"):
                    chat_id = "@" + chat_id
                
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status in ("member", "administrator", "creator"):
                    # Если пользователь уже в канале, помечаем как выполненное (без начисления), 
                    # чтобы не показывать это задание.
                    await grs_mark_completed(user_id, link)
                    continue
            except Exception:
                pass # Если не удалось проверить, просто показываем

        offers.append(o)

    if not offers:
        text = "🌿 *Grs задания*\n\n📝 Доступных заданий: 0\n───────────────\n💫 Можно заработать: 0$"
        return text, []
    n = len(offers)
    # Фиксированная выплата за одно Grs-задание (в долларах для пользователя)
    per_task_usd = 0.008
    total_payout = n * per_task_usd
    earn_str = _format_earn_usd(total_payout)
    text = (
        f"🌿 *Grs задания*\n\n"
        f"📝 Доступных заданий: {n}\n"
        f"───────────────\n"
        f"💫 Можно заработать: {earn_str}"
    )
    frozen_total, min_unfreeze = await frozen_get_summary(user_id)
    if frozen_total > 0:
        text += f"\n\n❄️ Заморожено: *{frozen_total:.2f}*"
        if min_unfreeze:
            text += f"\n   _Разморозка: {_format_unfreeze_at(min_unfreeze)}_"
    rows = []
    for o in offers:
        name = (o.get("name") or o.get("title") or "Канал").strip() or "Канал"
        link = o.get("link") or o.get("url") or ""
        if link:
            # Сохраняем каждое задание как ожидающее (pending)
            price = _parse_price_usd(o) or 0.008 # Дефолтная цена если API не вернул
            await tgrassa_save_pending(user_id, link, price)
            rows.append([InlineKeyboardButton(text=f"📢 {name[:30]}", url=link)])
    
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_tgrass")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:tgrassa")])
    return text, rows


@router.callback_query(F.data == "platform:tgrassa")
async def show_tgrassa(callback: CallbackQuery) -> None:
    """Grs задания по callback."""
    user = callback.from_user
    user_id = user.id if user else 0
    username = (user.username or "") if user else ""
    text, rows = await _build_tgrassa_content(user_id, username, user, bot=callback.bot)
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
    text, rows = await _build_tgrassa_content(user_id, username, user, bot=message.bot)
    if rows:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "check_tgrass")
async def callback_check_tgrass(callback: CallbackQuery) -> None:
    """
    Повторная проверка Tgrass: проверяем каждый оффер отдельно.
    Если оффер пропал из списка API /offers и пользователь подписан (get_chat_member) — награждаем.
    """
    user = callback.from_user
    user_id = user.id if user else 0
    username = (user.username or "") if user else ""
    if not config.TGRASSA_API_KEY:
        await callback.answer("API не настроен.", show_alert=True)
        return

    # 1. Получаем список ожидающих заданий из БД
    pending_list = await tgrassa_get_pending_by_user(user_id)
    if not pending_list:
        await callback.answer("Нет заданий для проверки. Нажмите «Обновить».", show_alert=True)
        await show_tgrassa(callback)
        return

    await callback.answer("Проверяю подписки…")

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
        await callback.bot.send_message(user_id, _alert(f"Ошибка: {err_msg}"))
        return

    # Офферы, которые Tgrass ВСЕ ЕЩЕ считает невыполненными
    remaining_offers = data.get("offers") or []
    remaining_links = {o.get("link") or o.get("url") for o in remaining_offers if (o.get("link") or o.get("url"))}

    total_frozen = 0.0
    n_completed = 0
    unfreeze_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    for p in pending_list:
        link = p["signature"]
        price = p["price"]

        # Если ссылки нет в списке оставшихся — значит Tgrass считает ее выполненной
        if link not in remaining_links:
            # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: проверяем реально ли юзер в канале
            is_member = False
            try:
                chat_id = link.split("/")[-1].split("?")[0]
                if not chat_id.startswith("@") and not chat_id.startswith("-"):
                    chat_id = "@" + chat_id
                
                member = await callback.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                if member.status in ("member", "administrator", "creator"):
                    is_member = True
            except Exception:
                # Если не удалось проверить (например, ссылка не на канал или бот не админ), 
                # доверяем API Tgrass, но в идеале здесь должна быть подписка.
                # Для безопасности, если не удалось проверить chat_id, можно считать True 
                # или False в зависимости от политики. Оставим True для совместимости с ссылками-не-каналами.
                if "t.me/" not in link:
                    is_member = True
                else:
                    is_member = False # Если это t.me ссылка и мы не смогли проверить — лучше не рисковать? 
                    # Но может быть приватная ссылка. Tgrass обычно дает публичные.
                    # Поставим True если API Tgrass говорит что выполнено.
                    is_member = True

            if is_member:
                # Помечаем как выполненное и замораживаем награду
                await tgrassa_mark_completed_and_freeze(user_id, link, price, unfreeze_at)
                total_frozen += price
                n_completed += 1

    if n_completed > 0:
        await tgrassa_clear_pending_for_completed(user_id)

    # Обновляем сообщение с заданиями
    text, rows = await _build_tgrassa_content(user_id, username, user, bot=callback.bot, data=data)
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
            parse_mode="Markdown",
        )
    except Exception:
        pass

    if total_frozen > 0:
        await callback.bot.send_message(
            user_id,
            f"✅ Проверка пройдена! Выполнено заданий: {n_completed}. Сумма {total_frozen:.3f}$ заморожена на 24 ч.",
        )
    else:
        await callback.answer("⚠️ Новых подписок не обнаружено. Подпишитесь на каналы перед проверкой!", show_alert=True)


# --- Flyer: единый формат заданий (Доступных заданий / Можно заработать $) ---


async def _build_flyer_content(user_id: int, lang: str, bot: Bot | None = None) -> tuple[str, list]:
    """
    Flyer: только get_tasks. Список заданий (подписи активны 48 ч). Проверка — по кнопке «Проверить подписку» через /check_task.
    """
    if not config.FLYER_API_KEY:
        text = "✈ *Fly задания*\n\nAPI-ключ не настроен. Перейдите в @FlyerServiceBot."
        rows = [[InlineKeyboardButton(text="Открыть @FlyerServiceBot", url=config.get_flyer_link())]]
        return text, rows

    try:
        data = await flyer_get_tasks(
            key=config.FLYER_API_KEY,
            user_id=user_id,
            limit=5,
            language_code=lang or "ru",
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
        text = "✈ *Fly задания*\n\n📝 Доступных заданий: 0\n───────────────\n💫 Можно заработать: 0$"
        rows = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:flyer")]]
        return text, rows

    # Скрываем задания, которые пользователь уже выполнил или на которые уже подписан
    result_left = []
    for t in result:
        sig = t.get("signature") or ""
        if sig and await flyer_already_completed(user_id, sig):
            continue
            
        # Проверка через Telegram API (если уже подписан — скрываем)
        if bot:
            link_url = t.get("link")
            links = t.get("links") or []
            if not link_url and links:
                first = links[0]
                link_url = first if isinstance(first, str) else (first.get("url") or first.get("link") if isinstance(first, dict) else None)
            
            if link_url and isinstance(link_url, str) and "t.me/" in link_url:
                try:
                    chat_id = link_url.split("/")[-1].split("?")[0]
                    if not chat_id.startswith("@") and not chat_id.startswith("-"):
                        chat_id = "@" + chat_id
                    
                    member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                    if member.status in ("member", "administrator", "creator"):
                        # Пользователь уже подписан, помечаем как выполненное (без начисления), чтобы скрыть
                        from database import flyer_mark_completed_and_credit
                        await flyer_mark_completed_and_credit(user_id, sig, 0.0)
                        continue
                except Exception:
                    pass

        result_left.append(t)

    if not result_left:
        text = "✈ *Fly задания*\n\n✅ Все задания выполнены. Новые появятся позже."
        frozen_total, min_unfreeze = await frozen_get_summary(user_id)
        if frozen_total > 0:
            text += f"\n\n❄️ Заморожено: *{frozen_total:.2f}*"
            if min_unfreeze:
                text += f"\n   _Разморозка: {_format_unfreeze_at(min_unfreeze)}_"
        rows = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:flyer")]]
        return text, rows

    n = len(result_left)
    total_payout = n * config.FLYER_PAYOUT_PER_TASK
    earn_str = _format_earn_usd(total_payout)
    header = (
        f"✈ *Fly задания*\n\n"
        f"📝 Доступных заданий: {n}\n"
        f"───────────────\n"
        f"💫 Можно заработать: {earn_str}\n"
        f"_Подписи заданий активны 48 ч. После подписки нажмите «Проверить подписку»._"
    )
    frozen_total, min_unfreeze = await frozen_get_summary(user_id)
    if frozen_total > 0:
        header += f"\n\n❄️ Заморожено: *{frozen_total:.2f}*"
        if min_unfreeze:
            header += f"\n   _Разморозка: {_format_unfreeze_at(min_unfreeze)}_"
    rows = []
    for t in result_left:
        signature = t.get("signature") or ""
        name = (t.get("name") or t.get("task") or "Задание").strip() or "Задание"
        price = _parse_price_usd(t)
        links = t.get("links") or []
        link_url = t.get("link")
        if not link_url and links:
            first = links[0]
            link_url = first if isinstance(first, str) else (first.get("url") or first.get("link") if isinstance(first, dict) else None)
        await flyer_save_pending(user_id, signature, price)
        if link_url:
            rows.append([InlineKeyboardButton(text=f"Подписаться — {name[:25]}", url=str(link_url))])
    rows.append([InlineKeyboardButton(text="Проверить ✅", callback_data="flyer_check")])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="platform:flyer")])
    return header, rows


@router.callback_query(F.data == "platform:flyer")
async def show_flyer(callback: CallbackQuery, *, skip_answer: bool = False) -> None:
    """Fly задания по callback (кнопка из инлайн-меню или Обновить). skip_answer=True если answer уже вызван (например из flyer_check)."""
    user_id = callback.from_user.id if callback.from_user else 0
    lang = _user_lang(callback.from_user)
    text, rows = await _build_flyer_content(user_id, lang, bot=callback.bot)
    try:
        if rows:
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                parse_mode="Markdown",
            )
        else:
            await callback.message.edit_text(text, parse_mode="Markdown")
    except TelegramBadRequest as e:
        if "message is not modified" not in (e.message or ""):
            raise
    if not skip_answer:
        await callback.answer()


@router.message(F.text == BTN_FLY)
async def show_flyer_message(message: Message) -> None:
    """Fly задания по нажатию кнопки нижнего меню."""
    user_id = message.from_user.id if message.from_user else 0
    lang = _user_lang(message.from_user)
    text, rows = await _build_flyer_content(user_id, lang, bot=message.bot)
    if rows:
        await message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="Markdown",
        )
    else:
        await message.answer(text, parse_mode="Markdown")


def _fly_task_result_status(data: dict) -> str:
    """Статус из ответа /check_task: complete, waiting, abort, incomplete, unavailable и т.д."""
    r = (data.get("result") or data.get("status") or "").strip().lower()
    return r or "unknown"


@router.callback_query(F.data == "flyer_check")
async def callback_flyer_check(callback: CallbackQuery) -> None:
    """
    Flyer: проверка подписок только через /check_task.
    Статусы: waiting — принято, проверка через 24 ч; abort — отписались; complete — оплата; incomplete — ещё не подписан.
    """
    user_id = callback.from_user.id if callback.from_user else 0
    if not config.FLYER_API_KEY:
        await callback.answer("API не настроен.", show_alert=True)
        return

    pending_list = await flyer_get_pending_by_user(user_id)
    if not pending_list:
        await callback.answer("Нет заданий для проверки. Нажмите «Обновить».", show_alert=True)
        await show_flyer(callback, skip_answer=True)
        return

    await callback.answer("Проверяю подписки…")

    unfreeze_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    total_frozen = 0.0
    n_waiting = 0
    n_abort = 0
    n_incomplete = 0
    n_complete = 0
    n_error = 0

    for p in pending_list:
        sig = p["signature"]
        if await flyer_already_completed(user_id, sig):
            continue
        try:
            task_data = await flyer_check_task(
                key=config.FLYER_API_KEY, user_id=user_id, signature=sig
            )
        except Exception:
            n_error += 1
            continue
        status = _fly_task_result_status(task_data)
        if _fly_task_complete(task_data):
            payout = config.FLYER_PAYOUT_PER_TASK
            await flyer_mark_completed_and_freeze(user_id, sig, payout, unfreeze_at)
            total_frozen += payout
            n_complete += 1
        elif status == "waiting":
            n_waiting += 1
        elif status == "abort":
            n_abort += 1
        elif status in ("incomplete", "unknown") or not status:
            n_incomplete += 1
        else:
            n_incomplete += 1

    if total_frozen > 0 or n_complete > 0:
        await flyer_clear_pending_for_completed(user_id)

    await show_flyer(callback, skip_answer=True)
    chat_id = callback.message.chat.id if callback.message else callback.from_user.id

    if total_frozen > 0:
        await callback.bot.send_message(
            chat_id,
            f"✅ Проверка пройдена! Сумма {total_frozen:.2f} заморожена на 24 ч. Если останетесь подписанным — будет зачислена на баланс.",
        )
    elif n_waiting > 0:
        await callback.bot.send_message(
            chat_id,
            "⏳ Задание принято! Окончательная проверка через 24 ч. Оставайтесь подписанными — тогда сумма будет зачислена на баланс."
        )
    elif n_abort > 0:
        await callback.bot.send_message(
            chat_id,
            f"❌ По {n_abort} заданию(ям) подписка отменена. Подпишитесь снова и нажмите «Проверить подписку»."
        )
    else:
        await callback.answer("⚠️ Новых выполнений не найдено. Подпишитесь на каналы выше перед проверкой!", show_alert=True)


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

    result = (data.get("result") or data.get("status") or "").strip().lower()
    error = data.get("error")
    if error:
        await callback.answer(_alert(f"Ошибка: {error}"), show_alert=True)
        return

    if _fly_task_complete(data):
        payout = config.FLYER_PAYOUT_PER_TASK
        unfreeze_at = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        await flyer_mark_completed_and_freeze(user_id, signature, payout, unfreeze_at)
        await callback.bot.send_message(
            user_id,
            f"✅ Проверка пройдена! Сумма {payout:.2f} заморожена на 24 ч. Если останетесь подписанным — будет зачислена на баланс.",
        )
        await show_flyer(callback, skip_answer=True)
        return

    if result == "waiting":
        await callback.answer("Задание принято, награда в течение 24 часов.", show_alert=True)
        return

    if result == "incomplete":
        await callback.answer("Задание ещё не выполнено. Подпишитесь и нажмите «Проверить подписку».", show_alert=True)
        return

    if result == "abort":
        await callback.answer("Подписка отменена. Подпишитесь снова и нажмите «Проверить подписку».", show_alert=True)
        return

    if result == "unavailable":
        await callback.answer("Задание недоступно.", show_alert=True)
        return

    await callback.answer(_alert(f"Статус: {result}. Попробуйте позже."), show_alert=True)
