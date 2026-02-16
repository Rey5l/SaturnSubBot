"""
Бот для заработка на заданиях (Tgrassa, Flyer) и вывода средств через Crypto Bot.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from database import init_db
from handlers import menu, platforms, balance, withdraw, admin, referral, info
from services.crypto_pay import close_client
from services.unfreeze_task import run_unfreeze_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot = None) -> None:
    """Инициализация при запуске."""
    await init_db()
    logger.info("База данных инициализирована")
    if bot is not None:
        asyncio.create_task(run_unfreeze_loop(bot))


async def on_shutdown() -> None:
    """Очистка при остановке."""
    await close_client()
    logger.info("Бот остановлен")


def main() -> None:
    if not config.BOT_TOKEN:
        logger.error("Укажите BOT_TOKEN в .env (скопируйте .env.example в .env)")
        sys.exit(1)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()

    async def _startup() -> None:
        await on_startup(bot)
        if not config.BOT_USERNAME:
            me = await bot.get_me()
            config.BOT_USERNAME = me.username or ""
            logger.info("BOT_USERNAME установлен из API: %s", config.BOT_USERNAME)
    dp.startup.register(_startup)
    dp.shutdown.register(on_shutdown)

    dp.include_router(menu.router)
    dp.include_router(platforms.router)
    dp.include_router(balance.router)
    dp.include_router(referral.router)
    dp.include_router(info.router)
    dp.include_router(withdraw.router)
    dp.include_router(admin.router)

    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
