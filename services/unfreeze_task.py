"""Фоновая задача: разморозка средств через 24 ч с проверкой подписки и уведомлением пользователя."""
import asyncio
import logging

import config
from database import frozen_get_due, frozen_release_and_credit, frozen_delete
from services.flyer_api import check_task as flyer_check_task
from services.tgrassa_api import tgrass_check

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 60


def _fly_task_complete(data: dict) -> bool:
    """Успешное выполнение задания Fly по ответу API (как в handlers.platforms)."""
    result = (data.get("result") or data.get("status") or "").lower().strip()
    return result in ("complete", "completed", "done", "success", "ok")


async def _process_due(bot) -> None:
    """Обработать все записи, у которых наступило время разморозки."""
    due = await frozen_get_due()
    for row in due:
        row_id = row["id"]
        user_id = row["user_id"]
        amount = row["amount"]
        platform = row["platform"]
        signature = row.get("signature")

        try:
            if platform == "grs":
                if not signature:
                    await frozen_delete(row_id)
                    continue
                
                # Строгая проверка подписки через Telegram API
                is_member = False
                try:
                    chat_id = signature.split("/")[-1].split("?")[0]
                    if not chat_id.startswith("@") and not chat_id.startswith("-"):
                        chat_id = "@" + chat_id
                    
                    member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                    if member.status in ("member", "administrator", "creator"):
                        is_member = True
                except Exception:
                    # Если не удалось проверить через API (например, ссылка не на канал),
                    # пробуем через API Tgrass
                    if not config.TGRASSA_API_KEY:
                        await frozen_delete(row_id)
                        continue
                    data = await tgrass_check(
                        key=config.TGRASSA_API_KEY,
                        tg_user_id=user_id,
                        tg_login="",
                        lang="ru",
                        is_premium=False,
                    )
                    remaining_offers = data.get("offers") or []
                    remaining_links = {o.get("link") or o.get("url") for o in remaining_offers if (o.get("link") or o.get("url"))}
                    if signature not in remaining_links:
                        is_member = True

                if is_member:
                    result = await frozen_release_and_credit(row_id)
                    if result:
                        _, credited = result
                        await bot.send_message(
                            user_id,
                            f"❄️ Разморозка: сумма *{credited:.3f}$* зачислена на баланс за подписку на Tgrass. Спасибо!",
                            parse_mode="Markdown",
                        )
                else:
                    await frozen_delete(row_id)
            else:
                if not config.FLYER_API_KEY or not signature:
                    await frozen_delete(row_id)
                    continue
                data = await flyer_check_task(
                    key=config.FLYER_API_KEY,
                    user_id=user_id,
                    signature=signature,
                )
                if _fly_task_complete(data):
                    result = await frozen_release_and_credit(row_id)
                    if result:
                        _, credited = result
                        await bot.send_message(
                            user_id,
                            f"❄️ Разморозка: сумма *{credited:.2f}* зачислена на баланс. Спасибо, что остаётесь с нами!",
                            parse_mode="Markdown",
                        )
                else:
                    await frozen_delete(row_id)
        except Exception as e:
            logger.exception("Ошибка разморозки row_id=%s: %s", row_id, e)


async def run_unfreeze_loop(bot) -> None:
    """Запуск цикла проверки замороженных средств и разморозки."""
    logger.info("Фоновая задача разморозки запущена (интервал %s с)", CHECK_INTERVAL_SEC)
    while True:
        try:
            await _process_due(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception("Ошибка в цикле разморозки: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SEC)
