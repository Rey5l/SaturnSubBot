"""Проверка обязательных подписок через Telegram API getChatMember."""
import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import get_mandatory_channels

logger = logging.getLogger(__name__)

MANDATORY_CHECK_CALLBACK = "mandatory_check"
SUBSCRIPTION_MESSAGE = (
    "🔒 *Чтобы пользоваться ботом, подпишитесь на каналы ниже.*\n\n"
    "После подписки нажмите «Проверить подписку». Если вы отпишетесь — доступ будет снова ограничен."
)

# Статусы, при которых пользователь считается подписанным
SUBSCRIBED_STATUSES = (
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    "member",
    "administrator",
    "creator",
)


async def check_mandatory_subscription(bot: Bot, user_id: int) -> tuple[bool, list[dict]]:
    """
    Проверить, подписан ли пользователь на все обязательные каналы.
    Возвращает (all_ok, list_of_channels_not_subscribed).
    """
    channels = await get_mandatory_channels()
    if not channels:
        return True, []

    not_subscribed = []
    for ch in channels:
        chat_id = ch.get("channel_id") or ch.get("channel_username") or ""
        if not chat_id:
            continue
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            status = getattr(member, "status", None) or ""
            if status not in SUBSCRIBED_STATUSES:
                not_subscribed.append(ch)
        except Exception as e:
            logger.warning("Ошибка проверки подписки %s для user %s: %s", chat_id, user_id, e)
            not_subscribed.append(ch)
    return len(not_subscribed) == 0, not_subscribed


def build_subscription_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    """Собрать инлайн-клавиатуру с кнопками каналов и «Проверить подписку»."""
    rows = []
    for ch in channels:
        title = (ch.get("title") or ch.get("channel_username") or "Канал").strip()[:30]
        link = (ch.get("invite_link") or "").strip()
        if not link:
            username = (ch.get("channel_username") or "").strip().lstrip("@")
            link = f"https://t.me/{username}" if username else ""
        if link:
            rows.append([InlineKeyboardButton(text=f"📢 {title}", url=link)])
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data=MANDATORY_CHECK_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
