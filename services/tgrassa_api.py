"""
Клиент Tgrass API (tgrass.space).
POST /offers с заголовком Auth, тело: tg_user_id, tg_login, lang, is_premium.

Тело ответа (JSON):
  status: "ok" | "no_offers" | "not_ok"
  offers: список офферов (при status == "not_ok"), каждый элемент:
    - name или title: название канала/задания
    - link или url: ссылка
    - price / reward / amount / pay (опционально): награда (число)
"""
import logging

import aiohttp

from config import TGRASSA_API_BASE, TGRASSA_API_SSL_VERIFY

logger = logging.getLogger(__name__)


def _connector() -> aiohttp.TCPConnector:
    if TGRASSA_API_SSL_VERIFY:
        return aiohttp.TCPConnector()
    return aiohttp.TCPConnector(ssl=False)


async def tgrass_check(key: str, tg_user_id: int, tg_login: str = "", lang: str = "ru", is_premium: bool = False) -> dict:
    """
    Проверка подписок Tgrass. POST https://tgrass.space/offers.
    Возвращает тело ответа: { "status": "ok"|"no_offers"|"not_ok", "offers": [...] }.
    """
    payload = {
        "tg_user_id": tg_user_id,
        "tg_login": tg_login or "",
        "lang": lang,
        "is_premium": is_premium,
    }
    connector = _connector()
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(
            f"{TGRASSA_API_BASE}/offers",
            json=payload,
            headers={"Auth": key, "Content-Type": "application/json"},
        ) as resp:
            data = await resp.json()
            logger.debug("Tgrass /offers response body: %s", data)
            return data
