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
from middlewares.mandatory_subscription import MandatorySubscriptionMiddleware
from services.crypto_pay import close_client
from services.webhooks import run_webhook_server
from services.unfreeze_task import run_unfreeze_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


_tgrass_webhook_runner = None


async def on_startup(bot: Bot = None) -> None:
    """Инициализация при запуске."""
    global _tgrass_webhook_runner
    await init_db()
    logger.info("База данных инициализирована")
    if bot is not None:
        # Удаляем вебхук, если он был установлен ранее (для работы polling)
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхук Telegram удалён (polling запущен)")
        asyncio.create_task(run_unfreeze_loop(bot))
    if config.TGRASSA_WEBHOOK_PORT > 0:
        _tgrass_webhook_runner = await run_webhook_server(config.TGRASSA_WEBHOOK_PORT, bot)


async def on_shutdown() -> None:
    """Очистка при остановке."""
    global _tgrass_webhook_runner
    if _tgrass_webhook_runner is not None:
        await _tgrass_webhook_runner.cleanup()
        _tgrass_webhook_runner = None
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

    dp.message.middleware(MandatorySubscriptionMiddleware())
    dp.callback_query.middleware(MandatorySubscriptionMiddleware())

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
