"""Сервис Crypto Pay API: баланс приложения и вывод пользователям."""
import uuid
from aiocryptopay import AioCryptoPay, Networks

import config
from database import deduct_balance, save_withdrawal, withdrawal_exists

_network = Networks.TEST_NET if config.CRYPTO_PAY_NETWORK == "TEST_NET" else Networks.MAIN_NET
_client: AioCryptoPay | None = None


def get_client() -> AioCryptoPay | None:
    """Вернуть клиент Crypto Pay или None, если не настроен."""
    global _client
    if not config.CRYPTO_PAY_ENABLED:
        return None
    if _client is None:
        _client = AioCryptoPay(
            token=config.CRYPTO_PAY_API_TOKEN,
            network=_network,
        )
    return _client


async def close_client() -> None:
    """Закрыть сессию клиента."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def get_app_balance() -> list[dict]:
    """Баланс приложения Crypto Pay (по валютам)."""
    client = get_client()
    if not client:
        return []
    balances = await client.get_balance()
    return [
        {"asset": b.currency_code, "available": float(b.available), "onhold": float(getattr(b, "onhold", 0) or 0)}
        for b in balances
    ]


async def get_asset_balance(asset: str) -> float:
    """Доступный баланс по одной валюте (например USDT)."""
    balances = await get_app_balance()
    for b in balances:
        if b["asset"] == asset:
            return b["available"]
    return 0.0


async def transfer_to_user(
    user_id: int,
    amount: float,
    asset: str | None = None,
    comment: str | None = None,
    deduct_user_balance: bool = True,
) -> tuple[bool, str]:
    """
    Вывод средств пользователю в Crypto Bot.
    Если deduct_user_balance=True, списываем сумму с виртуального баланса пользователя.
    Возвращает (успех, сообщение).
    """
    client = get_client()
    if not client:
        return False, "Вывод через Crypto Bot не настроен."

    asset = (asset or config.WITHDRAW_ASSET).upper()
    if amount < config.MIN_WITHDRAW_AMOUNT:
        return False, f"Минимальная сумма вывода: {config.MIN_WITHDRAW_AMOUNT} {asset}"

    app_balance = await get_asset_balance(asset)
    if app_balance < amount:
        return False, f"Недостаточно средств в кассе приложения. Доступно: {app_balance:.2f} {asset}"

    if deduct_user_balance:
        try:
            await deduct_balance(user_id, amount)
        except ValueError as e:
            return False, str(e)

    spend_id = str(uuid.uuid4())
    if await withdrawal_exists(spend_id):
        return False, "Повторный запрос с тем же ID. Попробуйте снова."

    try:
        transfer = await client.transfer(
            user_id=user_id,
            asset=asset,
            amount=round(amount, 8),
            spend_id=spend_id,
            comment=comment or "Вывод с EarnMoneyBot",
        )
    except Exception as e:
        if deduct_user_balance:
            # Вернуть баланс при ошибке API
            from database import add_balance
            await add_balance(user_id, amount)
        return False, f"Ошибка Crypto Pay: {e}"

    await save_withdrawal(user_id, amount, asset, spend_id, status="completed")
    return True, f"Выведено {amount} {asset}. Средства поступят в @CryptoBot."
