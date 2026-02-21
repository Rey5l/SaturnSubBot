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
                status = (data.get("status") or "").lower()
                if status in ("ok", "no_offers"):
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
