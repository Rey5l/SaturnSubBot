"""
Клиент Flyer API (api.flyerservice.io).
Документация: @FlyerServiceBot, Python: pip install flyerapi
"""
import aiohttp

from config import FLYER_API_SSL_VERIFY

FLYER_API_BASE = "https://api.flyerservice.io"


def _connector() -> aiohttp.TCPConnector:
    if FLYER_API_SSL_VERIFY:
        return aiohttp.TCPConnector()
    return aiohttp.TCPConnector(ssl=False)


async def _post(path: str, json: dict) -> dict:
    connector = _connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(f"{FLYER_API_BASE}{path}", json=json) as resp:
            return await resp.json()


async def get_me(key: str) -> dict:
    """Получить данные ключа. POST /get_me."""
    return await _post("/get_me", {"key": key})


async def flyer_check(key: str, user_id: int, language_code: str | None = None) -> dict:
    """
    Проверка подписок Flyer. Используется метод /check.
    POST https://api.flyerservice.io/check.
    Body: {"key", "user_id", "language_code"}.
    Ответ: skip=true → подписки проверены, доступ открыт; skip=false → показать задачи из /get_tasks.
    """
    payload: dict = {"key": key, "user_id": user_id}
    if language_code:
        payload["language_code"] = language_code
    return await _post("/check", payload)


async def get_tasks(
    key: str,
    user_id: int,
    limit: int = 10,
    language_code: str | None = None,
) -> dict:
    """
    Получить задания. POST https://api.flyerservice.io/get_tasks.
    Body: {"key", "user_id", "language_code", "limit"}. Подписи заданий активны 48 ч.
    """
    payload: dict = {"key": key, "user_id": user_id, "limit": limit}
    if language_code:
        payload["language_code"] = language_code
    return await _post("/get_tasks", payload)


async def check_task(key: str, user_id: int, signature: str) -> dict:
    """
    Проверить статус задания. POST /check_task.
    Ответ: {"result": "string", "error": "string"}.
    result: waiting — подписан, проверка через 24 ч; abort — отписался; complete — прошло 24 ч, подписан, оплата; incomplete — ещё не подписан.
    """
    return await _post("/check_task", {"key": key, "user_id": user_id, "signature": signature})


async def get_completed_tasks(key: str, user_id: int) -> dict:
    """Получить выполненные задания пользователя. POST /get_completed_tasks."""
    return await _post("/get_completed_tasks", {"key": key, "user_id": user_id})
