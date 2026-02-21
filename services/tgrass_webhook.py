"""
Приём webhook от Tgrass: при отписке Tgrass отправляет POST на ваш URL.
Тело: {"tg_user_id": 12344566, "offer_link": "https://t.me/telegram", "status": "unsubscribed"}
"""
import logging

import aiohttp.web

import config
from database import grs_save_webhook_event

logger = logging.getLogger(__name__)


async def handle_tgrass_webhook(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """
    POST /webhook/tgrass (или путь из TGRASSA_WEBHOOK_PATH).
    Тело: tg_user_id, offer_link, status (например unsubscribed).
    """
    if request.method != "POST":
        return aiohttp.web.Response(status=405, text="Method Not Allowed")

    try:
        body = await request.json()
    except Exception as e:
        logger.warning("Tgrass webhook: невалидный JSON: %s", e)
        return aiohttp.web.Response(status=400, text="Invalid JSON")

    tg_user_id = body.get("tg_user_id")
    offer_link = body.get("offer_link") or ""
    status = (body.get("status") or "").strip().lower()

    if tg_user_id is None:
        return aiohttp.web.Response(status=400, text="Missing tg_user_id")

    try:
        tg_user_id = int(tg_user_id)
    except (TypeError, ValueError):
        return aiohttp.web.Response(status=400, text="Invalid tg_user_id")

    try:
        await grs_save_webhook_event(tg_user_id, offer_link, status or "unknown")
    except Exception as e:
        logger.exception("Tgrass webhook: ошибка сохранения события: %s", e)
        return aiohttp.web.Response(status=500, text="Internal Error")

    logger.info("Tgrass webhook: tg_user_id=%s offer_link=%s status=%s", tg_user_id, offer_link, status)
    return aiohttp.web.Response(status=200, text="OK")


def create_app() -> aiohttp.web.Application:
    app = aiohttp.web.Application()
    path = (config.TGRASSA_WEBHOOK_PATH or "/webhook/tgrass").strip("/") or "webhook/tgrass"
    app.router.add_post(f"/{path}", handle_tgrass_webhook)
    return app


async def run_webhook_server(port: int) -> aiohttp.web.AppRunner:
    """Запустить HTTP-сервер для приёма webhook Tgrass. Возвращает runner для cleanup при остановке."""
    app = create_app()
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    path = (config.TGRASSA_WEBHOOK_PATH or "/webhook/tgrass").strip("/") or "webhook/tgrass"
    logger.info("Tgrass webhook: приём POST на http://0.0.0.0:%s/%s", port, path)
    return runner
