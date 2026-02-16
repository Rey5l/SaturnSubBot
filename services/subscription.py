"""Проверка подписки пользователя на канал через Telegram Bot API."""
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ChatMemberStatus


async def check_subscription(bot: Bot, channel_username: str, user_id: int) -> bool:
    """
    Проверить, подписан ли user_id на канал.
    channel_username: без @ (например "channelname" или "durov).
    Возвращает True если пользователь в канале (member, administrator, etc).
    Важно: бот должен быть добавлен в канал (хотя бы как участник), иначе getChatMember может не сработать для приватных каналов.
    """
    chat_id = f"@{channel_username}" if not channel_username.startswith("@") else channel_username
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramBadRequest:
        return False
    return member.status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    )
