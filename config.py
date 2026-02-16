"""Конфигурация бота."""
import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

# Путь к БД
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "bot.db"

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Crypto Pay (опционально; если не указан — вывод будет отключён)
CRYPTO_PAY_API_TOKEN = os.getenv("CRYPTO_PAY_API_TOKEN", "").strip()
CRYPTO_PAY_NETWORK = os.getenv("CRYPTO_PAY_NETWORK", "MAIN_NET").strip().upper()
WITHDRAW_ASSET = os.getenv("WITHDRAW_ASSET", "USDT").strip().upper()
MIN_WITHDRAW_AMOUNT = float(os.getenv("MIN_WITHDRAW_AMOUNT", "1"))

# Админы (могут зачислять баланс)
_admin_ids = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _admin_ids.split(",") if x.strip()]

# Ссылки на платформы заданий (базовые, без start)
TGRASSA_BOT_LINK = os.getenv("TGRASSA_BOT_LINK", "https://t.me/tgrassbot").strip()
FLYER_BOT_LINK = os.getenv("FLYER_BOT_LINK", "https://t.me/FlyerServiceBot").strip()

# API-ключи/токены платформ — передаются в ?start= при переходе в бота (чтобы выдавали задания)
TGRASSA_API_KEY = os.getenv("TGRASSA_API_KEY", "").strip()
FLYER_API_KEY = os.getenv("FLYER_API_KEY", "").strip()

# Tgrass API (tgrass.space): POST /offers, заголовок Auth: <ключ>
# По умолчанию SSL не проверяем (на macOS часто ошибка сертификата). Для включения: true
TGRASSA_API_BASE = os.getenv("TGRASSA_API_BASE", "https://tgrass.space").strip().rstrip("/")
TGRASSA_API_SSL_VERIFY = os.getenv("TGRASSA_API_SSL_VERIFY", "false").strip().lower() in ("1", "true", "yes")

# Проверка SSL при запросах к Flyer API (false — отключить, если ошибка сертификата на macOS)
FLYER_API_SSL_VERIFY = os.getenv("FLYER_API_SSL_VERIFY", "true").strip().lower() in ("1", "true", "yes")

# Доля от награды задания, которую получает пользователь (остальное — маржа бота). 0.0–1.0.
# Например 0.70: с задания 1$ пользователь получает 0.70$, бот оставляет 0.30$.
TGRASSA_PAYOUT_RATE = float(os.getenv("TGRASSA_PAYOUT_RATE", "0.70"))
FLYER_PAYOUT_RATE = float(os.getenv("FLYER_PAYOUT_RATE", "0.70"))


def get_tgrassa_link() -> str:
    """Ссылка на Tgrassa: с start=KEY если ключ задан (Telegram limit 64 байта)."""
    base = TGRASSA_BOT_LINK.rstrip("/")
    if TGRASSA_API_KEY:
        raw = TGRASSA_API_KEY[:64] if len(TGRASSA_API_KEY) > 64 else TGRASSA_API_KEY
        start = quote(raw, safe="")
        return f"{base}?start={start}" if "?" not in base else f"{base}&start={start}"
    return base


def get_flyer_link() -> str:
    """Ссылка на Flyer: с start=KEY если ключ задан (Telegram limit 64 байта)."""
    base = FLYER_BOT_LINK.rstrip("/")
    if FLYER_API_KEY:
        raw = FLYER_API_KEY[:64] if len(FLYER_API_KEY) > 64 else FLYER_API_KEY
        start = quote(raw, safe="")
        return f"{base}?start={start}" if "?" not in base else f"{base}&start={start}"
    return base

# Имя бота для реферальной ссылки (без @), например: SaturnEarnBot
BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()

# Доступность вывода
CRYPTO_PAY_ENABLED = bool(CRYPTO_PAY_API_TOKEN)

# Реферальный бонус (доля от вывода приглашённого, 0.30 = 30%)
REFERRAL_BONUS_RATE = float(os.getenv("REFERRAL_BONUS_RATE", "0.30"))
