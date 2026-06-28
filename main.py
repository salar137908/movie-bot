import asyncio
import html
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    FSInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.client.default import DefaultBotProperties

import crud
from config import (
    ADMIN_IDS,
    ARCHIVE_CHANNEL_ID,
    BOT_TOKEN,
    DATABASE_URL,
    POST_CHANNEL_ID,
    DELETE_AFTER_SECONDS,
    AUTO_BACKUP_ENABLED,
    AUTO_BACKUP_HOURS,
    AUTO_BACKUP_ON_START,
    REQUIRED_CHANNEL,
    REQUIRED_CHANNEL_LINK,
    SKIP_MEMBERSHIP_FOR_ADMINS,
)
from database import init_db

# ============================================================
# مرکز کنترل متن‌ها و دکمه‌ها
# ============================================================
BOT_VERSION = "movie-bot-v9.3-broadcast-buttons-fix"
BOT_TITLE = "🎬 ربات دریافت فایل"
WELCOME_TEXT = "سلام 👋\nبرای دریافت فایل، از لینک مخصوص داخل کانال وارد ربات شوید."
ADMIN_WELCOME_TEXT = "سلام ادمین 👋\nاز منوی زیر فایل‌ها را مدیریت کن."

BTN_ADD_FILE = "➕ ثبت فایل"
BTN_FILES = "📋 لیست فایل‌ها"
BTN_STATS = "📊 آمار"
BTN_BACKUP = "💾 بکاپ دیتابیس"
BTN_CREATE_CHANNEL_POST = "📤 ساخت پست کانال"
BTN_POSTS = "📋 لیست پست‌های کانال"
BTN_BROADCAST = "📣 ارسال همگانی"
BTN_HELP = "📌 راهنما"
BTN_CHANNELS = "📢 کانال‌های اجباری"
BTN_SECTION_CHANNELS = "🧩 کانال‌های بخش‌ها"
BTN_ADD_REQUIRED_CHANNEL = "➕ مدیریت و افزودن کانال اجباری"

BTN_USER_TELEGRAM = "📢 کانال تلگرام"
BTN_USER_VPN_PREMIUM = "🔐 فیلترشکن پرمیوم رایگان"
BTN_USER_ACCOUNTS = "💎 دریافت اکانت های پولی سایت های معروف"
BTN_USER_CONTACT = "☎️ ارتباط با تیم ما"
BTN_USER_EARN = "💰 کسب درآمد"
TEAM_LINK = "https://t.me/NeoSeoTeam"

JOIN_REQUIRED_TEXT = "🔒 شما هنوز در کانال‌های زیر عضو نشده‌اید.\n\nبعد از عضویت، به ربات برگرد و روی «✅ بررسی عضویت» بزن 👇"
BTN_JOIN_CHANNEL = "📢 عضویت در کانال"
BTN_CHECK_JOIN = "✅ بررسی عضویت"

FILE_NOT_FOUND_TEXT = "❌ این فایل پیدا نشد یا غیرفعال شده است."
FILE_SENDING_TEXT = "⏳ فایل در حال ارسال است..."
FILE_WARNING_TEXT = "⚠️ این فایل بعد از ۱۵ ثانیه حذف می‌شود.\n\nاگر نیاز دارید، همین حالا آن را در Saved Messages تلگرام ذخیره کنید."

# اگر نمی‌خواهی پیام دیباگ حذف برای ادمین بیاید، False بماند.
DELETE_DEBUG_TO_ADMIN = False


SECTION_TITLES: dict[str, str] = {
    "telegram": BTN_USER_TELEGRAM,
    "vpn": BTN_USER_VPN_PREMIUM,
    "accounts": BTN_USER_ACCOUNTS,
    "contact": BTN_USER_CONTACT,
}

SECTION_BUTTON_TO_KEY: dict[str, str] = {
    BTN_USER_TELEGRAM: "telegram",
    BTN_USER_VPN_PREMIUM: "vpn",
    BTN_USER_ACCOUNTS: "accounts",
    # ارتباط با تیم ما لینک مستقیم دارد و عضویت اجباری جداگانه ندارد.
}

SECTION_RESULT_TEXTS: dict[str, str] = {
    "telegram": "✅ عضویت تایید شد.\n\n📢 دسترسی بخش کانال تلگرام فعال شد.",
    "vpn": "✅ عضویت تایید شد.\n\n🔐 بخش فیلترشکن پرمیوم رایگان فعال شد.\nمتن یا لینک نهایی این بخش را می‌توان بعداً داخل کد تنظیم کرد.",
    "accounts": "✅ عضویت تایید شد.\n\n💎 دسترسی این بخش فعال شد.\nفقط اطلاعاتی را قرار بده که مجوز انتشارش را داری.",
    "contact": "☎️ ارتباط با تیم ما\n\nبرای ارتباط با تیم، پیام خودت را همینجا بفرست یا آیدی پشتیبانی را داخل متن این بخش قرار بده.\n\nاین گزینه عضویت اجباری جداگانه ندارد.",
}

SECTION_KEY_HELP = "telegram | vpn | accounts | contact"



# نکته: چون پیام‌ها با HTML ارسال می‌شوند، داخل متن راهنما از <ID> استفاده نکن.
# تلگرام آن را مثل تگ HTML می‌خواند و خطای BadRequest می‌دهد.
ADMIN_HELP_TEXT = """
📌 راهنمای ادمین

➕ ثبت فایل:
از دکمه «➕ ثبت فایل» یا دستور /add استفاده کن، عنوان را بفرست و بعد فایل را از کانال آرشیو فوروارد کن.

📋 لیست فایل‌ها:
/files

📤 ساخت پست کانال:
از دکمه «📤 ساخت پست کانال» یا دستور /post استفاده کن.

📣 ارسال همگانی:
از دکمه «📣 ارسال همگانی» یا دستور /broadcast استفاده کن. متن و مدیا را می‌فرستی؛ برای هر دکمه متن و لینک را جدا می‌فرستی، رنگ را با گزینه شیشه‌ای انتخاب می‌کنی و تا ۱۰ دکمه می‌سازی.

📢 مدیریت کانال‌های اجباری:
از دکمه «📢 کانال‌های اجباری» یا دستور /channels استفاده کن.
در این بخش می‌توانی کانال‌های عضویت اجباری شروع ربات، فیلترشکن، اکانت‌ها و کانال تلگرام را جدا مدیریت کنی.

➕ افزودن کانال اجباری:
/addchannel
این دستور خالی کانال اضافه نمی‌کند؛ فقط منوی انتخاب بخش را باز می‌کند.

مسیر پیشنهادی:
📢 کانال‌های اجباری → انتخاب بخش → افزودن کانال جدید → ارسال @username

نکته:
گزینه «ارتباط با تیم ما» عضویت اجباری جداگانه ندارد.
""".strip()

# ============================================================

router = Router()


class AddFileState(StatesGroup):
    title = State()
    forwarded_file = State()


class EditFileState(StatesGroup):
    title = State()


class SetFileLinkChannelsState(StatesGroup):
    channels = State()


class CreateChannelPostState(StatesGroup):
    text = State()
    media = State()
    buttons = State()
    target_channels = State()


class BroadcastState(StatesGroup):
    content = State()
    confirm = State()


class AddSectionChannelState(StatesGroup):
    channel = State()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)



def team_link_kb(text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, url=TEAM_LINK)]
        ]
    )



def inline_user_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BTN_USER_TELEGRAM, callback_data="usersec:telegram")],
            [InlineKeyboardButton(text=BTN_USER_VPN_PREMIUM, callback_data="usersec:vpn")],
            [InlineKeyboardButton(text=BTN_USER_ACCOUNTS, callback_data="usersec:accounts")],
            [InlineKeyboardButton(text=BTN_USER_CONTACT, url=TEAM_LINK)],
            [InlineKeyboardButton(text=BTN_USER_EARN, url=TEAM_LINK)],
        ]
    )


def user_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_USER_TELEGRAM)],
            [KeyboardButton(text=BTN_USER_VPN_PREMIUM)],
            [KeyboardButton(text=BTN_USER_ACCOUNTS)],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_USER_TELEGRAM), KeyboardButton(text=BTN_USER_VPN_PREMIUM)],
            [KeyboardButton(text=BTN_USER_ACCOUNTS), KeyboardButton(text=BTN_USER_CONTACT)],
            [KeyboardButton(text=BTN_USER_EARN)],
            [KeyboardButton(text=BTN_ADD_FILE), KeyboardButton(text=BTN_FILES)],
            [KeyboardButton(text=BTN_CREATE_CHANNEL_POST), KeyboardButton(text=BTN_POSTS)],
            [KeyboardButton(text=BTN_BROADCAST)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_BACKUP)],
            [KeyboardButton(text=BTN_CHANNELS)],
            [KeyboardButton(text=BTN_ADD_REQUIRED_CHANNEL)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def menu_for_user(user_id: int) -> ReplyKeyboardMarkup:
    return admin_menu() if is_admin(user_id) else user_menu()

def add_required_channel_target_kb() -> InlineKeyboardMarkup:
    """Admin helper: choose where the forced-join channel should be used."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 عضویت اجباری شروع ربات", callback_data="addgate:main")],
            [InlineKeyboardButton(text="🔐 فیلترشکن پرمیوم رایگان", callback_data="addgate:vpn")],
            [InlineKeyboardButton(text="💎 اکانت های پولی سایت های معروف", callback_data="addgate:accounts")],
            [InlineKeyboardButton(text="📢 کانال تلگرام", callback_data="addgate:telegram")],
        ]
    )


# ============================================================
# پنل شیشه‌ای مدیریت کانال‌های اجباری برای ادمین
# ============================================================

CHANNEL_MANAGER_TARGETS: dict[str, str] = {
    "main": "🚪 عضویت اجباری شروع ربات",
    "vpn": BTN_USER_VPN_PREMIUM,
    "accounts": BTN_USER_ACCOUNTS,
    "telegram": BTN_USER_TELEGRAM,
}


def channel_manager_root_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚪 عضویت اجباری شروع ربات", callback_data="managegate:main")],
            [InlineKeyboardButton(text=BTN_USER_VPN_PREMIUM, callback_data="managegate:vpn")],
            [InlineKeyboardButton(text=BTN_USER_ACCOUNTS, callback_data="managegate:accounts")],
            [InlineKeyboardButton(text=BTN_USER_TELEGRAM, callback_data="managegate:telegram")],
            [InlineKeyboardButton(text="➕ افزودن کانال اجباری", callback_data="manageaddmenu")],
        ]
    )


async def send_channel_manager_root(message_or_call) -> None:
    text = (
        "📢 <b>مدیریت کانال‌های اجباری</b>\n\n"
        "اول بخش مورد نظر را انتخاب کن. بعد از انتخاب بخش، لیست کانال‌های همان بخش نمایش داده می‌شود.\n\n"
        "داخل هر بخش این گزینه‌ها را داری:\n"
        "➕ افزودن کانال جدید\n"
        "✏️ ادیت کانال\n"
        "🗑 حذف کانال\n\n"
        "• عضویت اجباری شروع ربات: فقط برای /start معمولی\n"
        "• فیلترشکن پرمیوم رایگان: فقط برای همان گزینه\n"
        "• اکانت‌های پولی: فقط برای همان گزینه\n"
        "• کانال تلگرام: فقط برای همان گزینه\n\n"
        "گزینه ارتباط با تیم ما عضویت اجباری جداگانه ندارد."
    )
    if isinstance(message_or_call, CallbackQuery):
        try:
            await message_or_call.message.edit_text(text, reply_markup=channel_manager_root_kb())
        except Exception:
            await message_or_call.message.answer(text, reply_markup=channel_manager_root_kb())
        await message_or_call.answer()
    else:
        await message_or_call.answer(text, reply_markup=channel_manager_root_kb())


async def _target_channels(target: str, active_only: bool = True):
    if target == "main":
        return await crud.get_required_channels(active_only=active_only)
    return await crud.get_section_required_channels(section_key=target, active_only=active_only)


def _channel_item_text(ch, target: str) -> str:
    status = "✅ فعال" if getattr(ch, "is_active", False) else "❌ غیرفعال"
    section_line = "" if target == "main" else f"بخش: <b>{CHANNEL_MANAGER_TARGETS.get(target, target)}</b>\n"
    return (
        f"{status}\n"
        f"ID: <code>{ch.id}</code>\n"
        f"{section_line}"
        f"عنوان: <b>{getattr(ch, 'title', None) or '-'}</b>\n"
        f"Chat: <code>{getattr(ch, 'chat_id', '-') or '-'}</code>\n"
        f"Link: <code>{getattr(ch, 'link', None) or '-'}</code>"
    )


def channel_manager_list_kb(target: str, channels) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        title = getattr(ch, "title", None) or getattr(ch, "chat_id", "کانال")
        short_title = str(title)[:24]
        rows.append([InlineKeyboardButton(text=f"📌 {short_title}", callback_data=f"noop:{target}:{ch.id}")])
        rows.append([
            InlineKeyboardButton(text="✏️ ادیت", callback_data=f"manageedit:{target}:{ch.id}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"managedel:{target}:{ch.id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ افزودن کانال جدید", callback_data=f"manageadd:{target}")])
    rows.append([InlineKeyboardButton(text="🔙 برگشت به بخش‌ها", callback_data="manageback")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_channel_target_list(message_or_call, target: str) -> None:
    if target not in CHANNEL_MANAGER_TARGETS:
        if isinstance(message_or_call, CallbackQuery):
            await message_or_call.answer("بخش نامعتبر است.", show_alert=True)
        return
    channels = await _target_channels(target, active_only=True)
    title = CHANNEL_MANAGER_TARGETS[target]
    lines = [f"📢 <b>{title}</b>\n"]
    if not channels:
        lines.append("هنوز برای این بخش کانال فعالی ثبت نشده است. از دکمه افزودن استفاده کن.")
    else:
        lines.append("لیست کانال‌های فعال این بخش:\n")
        for ch in channels:
            lines.append(_channel_item_text(ch, target) + "\n")
    text = "\n".join(lines)
    kb = channel_manager_list_kb(target, channels)
    if isinstance(message_or_call, CallbackQuery):
        try:
            await message_or_call.message.edit_text(text, reply_markup=kb)
        except Exception:
            await message_or_call.message.answer(text, reply_markup=kb)
        await message_or_call.answer()
    else:
        await message_or_call.answer(text, reply_markup=kb)


async def get_join_channels() -> list[dict[str, str]]:
    """Active required channels from DB; fallback to .env if DB has no active channels."""
    db_channels = await crud.get_required_channels(active_only=True)
    if db_channels:
        return [
            {
                "chat_id": str(ch.chat_id),
                "title": ch.title or str(ch.chat_id),
                "link": ch.link or "",
            }
            for ch in db_channels
        ]

    if REQUIRED_CHANNEL:
        return [
            {
                "chat_id": REQUIRED_CHANNEL,
                "title": REQUIRED_CHANNEL,
                "link": REQUIRED_CHANNEL_LINK or "",
            }
        ]

    return []


async def is_joined_channel(bot: Bot, user_id: int, chat_id: str) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        return False


async def get_missing_channels(bot: Bot, user_id: int, channels: list[dict[str, str]]) -> list[dict[str, str]]:
    """فقط کانال‌هایی را برمی‌گرداند که کاربر هنوز عضو آن‌ها نیست."""
    if is_admin(user_id) and SKIP_MEMBERSHIP_FOR_ADMINS:
        return []

    missing: list[dict[str, str]] = []
    for ch in channels:
        if not await is_joined_channel(bot, user_id, ch["chat_id"]):
            missing.append(ch)
    return missing


def missing_join_text(base_text: str, missing_channels: list[dict[str, str]] | None = None) -> str:
    # کانال‌هایی که کاربر عضو نیست فقط در دکمه‌های شیشه‌ای نمایش داده می‌شوند.
    # اسم کانال‌ها داخل متن پیام تکرار نمی‌شود تا پیام کوتاه و تمیز بماند.
    return base_text


async def join_keyboard(payload: str, bot: Bot | None = None, user_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    channels = await get_join_channels()

    if bot is not None and user_id is not None:
        channels = await get_missing_channels(bot, user_id, channels)

    for ch in channels:
        if ch.get("link"):
            title = ch.get("title") or "کانال"
            rows.append([InlineKeyboardButton(text=f"{BTN_JOIN_CHANNEL} {title}", url=ch["link"])])

    rows.append([InlineKeyboardButton(text=BTN_CHECK_JOIN, callback_data=f"check:{payload}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)




def extract_file_link_id_from_payload(payload: str | None) -> int | None:
    if not payload:
        return None
    match = re.fullmatch(r"l_(\d+)", payload.strip())
    if not match:
        return None
    return int(match.group(1))


async def get_file_link_join_channels(link_id: int) -> list[dict[str, str]]:
    db_channels = await crud.get_file_link_required_channels(link_id=link_id, active_only=True)
    return [
        {
            "chat_id": str(ch.chat_id),
            "title": ch.title or str(ch.chat_id),
            "link": ch.link or "",
            "id": str(ch.id),
            "link_id": str(ch.link_id),
        }
        for ch in db_channels
    ]


async def file_link_join_keyboard(link_id: int, bot: Bot | None = None, user_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    channels = await get_file_link_join_channels(link_id)

    if bot is not None and user_id is not None:
        channels = await get_missing_channels(bot, user_id, channels)

    for ch in channels:
        if ch.get("link"):
            title = ch.get("title") or "کانال"
            rows.append([InlineKeyboardButton(text=f"{BTN_JOIN_CHANNEL} {title}", url=ch["link"])])

    rows.append([InlineKeyboardButton(text=BTN_CHECK_JOIN, callback_data=f"link_check:{link_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def is_file_link_member(bot: Bot, user_id: int, link_id: int) -> bool:
    channels = await get_file_link_join_channels(link_id)
    if not channels:
        return True
    missing = await get_missing_channels(bot, user_id, channels)
    return len(missing) == 0



def file_link_join_text(link_id: int, missing_channels: list[dict[str, str]] | None = None) -> str:
    base = (
        "🔒 برای دریافت این فایل عضو کانال‌های زیر شوید.\n\n"
        "بعد از عضویت، به ربات برگرد و روی «✅ بررسی عضویت» بزن 👇"
    )
    return missing_join_text(base, missing_channels)


async def file_link_url(bot: Bot, link_id: int) -> str:
    me = await bot.get_me()
    return f"https://t.me/{me.username}?start=l_{link_id}"


def file_link_manage_kb(link_id: int, file_id: int | None = None, is_active: bool = True) -> InlineKeyboardMarkup:
    toggle_text = "⛔️ غیرفعال کردن لینک" if is_active else "✅ فعال کردن لینک"
    rows = [
        [InlineKeyboardButton(text="📢 تنظیم کانال‌های همین لینک", callback_data=f"setlinkch:{link_id}")],
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"linktoggle:{link_id}"),
            InlineKeyboardButton(text="📋 کانال‌های لینک", callback_data=f"linkchannels:{link_id}"),
        ],
    ]
    if file_id:
        rows.append([InlineKeyboardButton(text="➕ ساخت لینک جدید برای همین فایل", callback_data=f"newlink:{file_id}")])
        rows.append([InlineKeyboardButton(text="🔗 همه لینک‌های این فایل", callback_data=f"filelinks:{file_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_channel_lines(raw: str) -> list[tuple[str, str | None]]:
    lines = [ln.strip() for ln in str(raw or "").splitlines() if ln.strip()]
    if len(lines) == 1 and "," in lines[0]:
        lines = [ln.strip() for ln in lines[0].split(",") if ln.strip()]

    result: list[tuple[str, str | None]] = []
    for line in lines:
        parts = line.split(maxsplit=1)
        chat_id = parts[0].strip()
        link = parts[1].strip() if len(parts) > 1 else None
        if chat_id:
            result.append((chat_id, link))
    return result


async def get_section_join_channels(section_key: str) -> list[dict[str, str]]:
    db_channels = await crud.get_section_required_channels(section_key=section_key, active_only=True)
    return [
        {
            "chat_id": str(ch.chat_id),
            "title": ch.title or str(ch.chat_id),
            "link": ch.link or "",
            "id": str(ch.id),
            "section_key": ch.section_key,
        }
        for ch in db_channels
    ]


async def section_join_keyboard(section_key: str, bot: Bot | None = None, user_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    channels = await get_section_join_channels(section_key)

    if bot is not None and user_id is not None:
        channels = await get_missing_channels(bot, user_id, channels)

    for ch in channels:
        if ch.get("link"):
            title = ch.get("title") or "کانال"
            rows.append([InlineKeyboardButton(text=f"{BTN_JOIN_CHANNEL} {title}", url=ch["link"])])

    rows.append([InlineKeyboardButton(text=BTN_CHECK_JOIN, callback_data=f"section_check:{section_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def is_section_member(bot: Bot, user_id: int, section_key: str) -> bool:
    channels = await get_section_join_channels(section_key)
    if not channels:
        return False
    missing = await get_missing_channels(bot, user_id, channels)
    return len(missing) == 0



def section_join_text(section_key: str, missing_channels: list[dict[str, str]] | None = None) -> str:
    title = SECTION_TITLES.get(section_key, "این بخش")
    base = (
        f"🔒 برای استفاده از بخش «{title}» عضو کانال‌های زیر شوید.\n\n"
        "بعد از عضویت، به ربات برگرد و روی «✅ بررسی عضویت» بزن 👇"
    )
    return missing_join_text(base, missing_channels)


async def send_section_flow(message: Message, section_key: str) -> None:
    if section_key not in SECTION_TITLES:
        await message.answer("❌ این بخش پیدا نشد.")
        return

    # گزینه ارتباط با تیم ما عضویت اجباری جداگانه ندارد.
    if section_key == "contact":
        await message.answer(
            SECTION_RESULT_TEXTS.get(section_key, "☎️ ارتباط با تیم ما"),
            reply_markup=menu_for_user(message.from_user.id),
        )
        return

    channels = await get_section_join_channels(section_key)
    if not channels:
        text = f"⚠️ برای بخش «{SECTION_TITLES[section_key]}» هنوز کانال عضویت تنظیم نشده است."
        if is_admin(message.from_user.id):
            text += "\n\nاز دکمه «📢 کانال‌های اجباری» بخش مورد نظر را انتخاب کن و کانال جدید اضافه کن."
        await message.answer(text, reply_markup=menu_for_user(message.from_user.id))
        return

    if not await is_section_member(message.bot, message.from_user.id, section_key):
        missing = await get_missing_channels(message.bot, message.from_user.id, channels)
        await message.answer(section_join_text(section_key, missing), reply_markup=await section_join_keyboard(section_key, message.bot, message.from_user.id))
        return

    await message.answer(
        SECTION_RESULT_TEXTS.get(section_key, "✅ عضویت تایید شد."),
        reply_markup=menu_for_user(message.from_user.id),
    )


def extract_file_id_from_payload(payload: str | None) -> int | None:
    if not payload:
        return None
    match = re.fullmatch(r"f_(\d+)", payload.strip())
    if not match:
        return None
    return int(match.group(1))


async def is_member(bot: Bot, user_id: int) -> bool:
    channels = await get_join_channels()
    if not channels:
        return True
    missing = await get_missing_channels(bot, user_id, channels)
    return len(missing) == 0


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            pass


async def delete_file_later(bot: Bot, chat_id: int, file_message_id: int, warning_message_id: int | None = None) -> None:
    """Delete only the sent file message, then delete the warning message.

    این تابع هیچ پیام جدیدی مثل «زمان مشاهده فایل تمام شد» نمی‌فرستد.
    فقط فایل ارسال‌شده و پیام هشدار را حذف می‌کند.
    """
    await asyncio.sleep(DELETE_AFTER_SECONDS)

    deleted = False
    last_error = ""

    for attempt in range(1, 4):
        try:
            await bot.delete_message(
                chat_id=chat_id,
                message_id=file_message_id
            )
            deleted = True

            if DELETE_DEBUG_TO_ADMIN:
                await notify_admins(
                    bot,
                    "✅ حذف خودکار فایل انجام شد\n\n"
                    f"Chat ID: <code>{chat_id}</code>\n"
                    f"File Message ID: <code>{file_message_id}</code>\n"
                    f"Attempt: <code>{attempt}</code>"
                )

            break

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            await asyncio.sleep(2)

    if not deleted:
        await notify_admins(
            bot,
            "⚠️ خطا در حذف خودکار فایل\n\n"
            f"Chat ID: <code>{chat_id}</code>\n"
            f"File Message ID: <code>{file_message_id}</code>\n"
            f"Error: <code>{last_error}</code>"
        )

    if warning_message_id:
        try:
            await bot.delete_message(
                chat_id=chat_id,
                message_id=warning_message_id
            )
        except Exception:
            pass

async def send_file_to_user(bot: Bot, chat_id: int, file_id: int) -> None:
    item = await crud.get_file(file_id)
    if item is None or not item.is_active:
        await bot.send_message(chat_id=chat_id, text=FILE_NOT_FOUND_TEXT)
        return

    status_msg = await bot.send_message(chat_id=chat_id, text=FILE_SENDING_TEXT)

    sent_message_id: int | None = None

    # روش اصلی و مطمئن:
    # فایل با file_id خود تلگرام ارسال می‌شود، سپس message_id برگشتی حذف می‌شود.
    try:
        if item.telegram_file_id and item.file_type == "video":
            sent = await bot.send_video(chat_id=chat_id, video=item.telegram_file_id, caption=item.title, protect_content=False)
            sent_message_id = sent.message_id
        elif item.telegram_file_id and item.file_type == "document":
            sent = await bot.send_document(chat_id=chat_id, document=item.telegram_file_id, caption=item.title, protect_content=False)
            sent_message_id = sent.message_id
        elif item.telegram_file_id and item.file_type == "animation":
            sent = await bot.send_animation(chat_id=chat_id, animation=item.telegram_file_id, caption=item.title, protect_content=False)
            sent_message_id = sent.message_id
        elif item.telegram_file_id and item.file_type == "audio":
            sent = await bot.send_audio(chat_id=chat_id, audio=item.telegram_file_id, caption=item.title, protect_content=False)
            sent_message_id = sent.message_id
        elif item.telegram_file_id and item.file_type == "voice":
            sent = await bot.send_voice(chat_id=chat_id, voice=item.telegram_file_id, caption=item.title, protect_content=False)
            sent_message_id = sent.message_id
        elif item.telegram_file_id and item.file_type == "photo":
            sent = await bot.send_photo(chat_id=chat_id, photo=item.telegram_file_id, caption=item.title, protect_content=False)
            sent_message_id = sent.message_id
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ این فایل با نسخه قدیمی ثبت شده و برای حذف خودکار دقیق مناسب نیست.\n\n"
                    "لطفاً ادمین فایل را یک‌بار دوباره با نسخه جدید ثبت کند."
                )
            )
            await notify_admins(
                bot,
                "⚠️ فایل قدیمی نیاز به ثبت مجدد دارد\n\n"
                f"File ID: <code>{file_id}</code>\n"
                f"Title: <code>{item.title}</code>\n"
                "دلیل: telegram_file_id داخل دیتابیس خالی است."
            )
            return

    except Exception as e:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ ارسال فایل انجام نشد. لطفاً به ادمین اطلاع بده.\n\nممکن است فایل قدیمی باشد یا ربات به آرشیو دسترسی نداشته باشد.",
        )
        await notify_admins(
            bot,
            "⚠️ خطا در ارسال فایل\n\n"
            f"File ID: <code>{file_id}</code>\n"
            f"Archive Chat: <code>{item.archive_chat_id}</code>\n"
            f"Archive Message: <code>{item.archive_message_id}</code>\n"
            f"File Type: <code>{getattr(item, 'file_type', None)}</code>\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return

    if sent_message_id is None:
        await notify_admins(
            bot,
            "⚠️ message_id فایل ارسال‌شده پیدا نشد.\n"
            f"File ID: <code>{file_id}</code>"
        )
        return

    # پیام «در حال ارسال» لازم نیست بماند.
    try:
        await bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
    except Exception:
        pass

    await crud.increment_views(file_id)
    warning = await bot.send_message(chat_id=chat_id, text=FILE_WARNING_TEXT)

    asyncio.create_task(
        delete_file_later(
            bot=bot,
            chat_id=chat_id,
            file_message_id=int(sent_message_id),
            warning_message_id=warning.message_id,
        )
    )

async def handle_file_request(message: Message, payload: str) -> None:
    link_id = extract_file_link_id_from_payload(payload)
    if link_id is not None:
        link_item = await crud.get_file_link(link_id)
        if link_item is None or not link_item.is_active:
            await message.answer(FILE_NOT_FOUND_TEXT)
            return

        channels = await get_file_link_join_channels(link_id)
        if channels and not await is_file_link_member(message.bot, message.from_user.id, link_id):
            missing = await get_missing_channels(message.bot, message.from_user.id, channels)
            await message.answer(file_link_join_text(link_id, missing), reply_markup=await file_link_join_keyboard(link_id, message.bot, message.from_user.id))
            return

        await crud.increment_file_link_views(link_id)
        await send_file_to_user(message.bot, message.chat.id, int(link_item.file_id))
        return

    file_id = extract_file_id_from_payload(payload)
    if file_id is None:
        await message.answer(WELCOME_TEXT)
        return

    # لینک‌های قدیمی f_ برای سازگاری قبلی همان گیت عمومی را چک می‌کنند.
    # لینک‌های جدید l_ فقط کانال‌های مخصوص همان لینک را چک می‌کنند.
    if not await is_member(message.bot, message.from_user.id):
        missing = await get_missing_channels(message.bot, message.from_user.id, await get_join_channels())
        await message.answer(missing_join_text(JOIN_REQUIRED_TEXT, missing), reply_markup=await join_keyboard(payload, message.bot, message.from_user.id))
        return

    await send_file_to_user(message.bot, message.chat.id, file_id)



@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("✅ عملیات فعلی لغو شد. حالا از منوی پایین ادامه بده.", reply_markup=admin_menu())


@router.message(Command("version"))
async def version_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(f"✅ نسخه فعال: <code>{BOT_VERSION}</code>")


@router.message(CommandStart())
async def start_handler(message: Message, command: CommandStart) -> None:
    await crud.save_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    payload = command.args
    if payload:
        await handle_file_request(message, payload)
        return

    # عضویت اجباری عمومی: کاربر اول عضو کانال‌های اصلی می‌شود، بعد منوی کاربر را می‌بیند.
    if not await is_member(message.bot, message.from_user.id):
        missing = await get_missing_channels(message.bot, message.from_user.id, await get_join_channels())
        await message.answer(missing_join_text(JOIN_REQUIRED_TEXT, missing), reply_markup=await join_keyboard("menu", message.bot, message.from_user.id))
        return

    if is_admin(message.from_user.id):
        await message.answer(ADMIN_WELCOME_TEXT, reply_markup=admin_menu())
    else:
        await message.answer("سلام 👋\nیکی از گزینه‌های زیر را انتخاب کن:", reply_markup=inline_user_menu())



@router.message(F.text == BTN_USER_CONTACT)
async def contact_team_handler(message: Message) -> None:
    await message.answer(
        "☎️ برای ارتباط با تیم ما روی دکمه زیر بزن:",
        reply_markup=team_link_kb("☎️ ارتباط با تیم ما"),
    )


@router.message(F.text == BTN_USER_EARN)
async def earn_money_handler(message: Message) -> None:
    await message.answer(
        "💰 برای هماهنگی درباره کسب درآمد روی دکمه زیر بزن:",
        reply_markup=team_link_kb("💰 کسب درآمد"),
    )



@router.callback_query(F.data.startswith("usersec:"))
async def user_section_inline_callback(call: CallbackQuery) -> None:
    section_key = call.data.split(":", 1)[1]
    if section_key not in SECTION_TITLES or section_key == "contact":
        await call.answer("بخش نامعتبر است.", show_alert=True)
        return

    await crud.save_user(
        telegram_id=call.from_user.id,
        username=call.from_user.username,
        full_name=call.from_user.full_name,
    )

    if not await is_member(call.bot, call.from_user.id):
        missing = await get_missing_channels(call.bot, call.from_user.id, await get_join_channels())
        await call.message.answer(missing_join_text(JOIN_REQUIRED_TEXT, missing), reply_markup=await join_keyboard("menu", call.bot, call.from_user.id))
        await call.answer("ابتدا عضویت را تکمیل کن.", show_alert=True)
        return

    await call.answer()
    await send_section_flow(call.message, section_key)


@router.message(F.text.in_(SECTION_BUTTON_TO_KEY.keys()))
async def user_section_button_handler(message: Message) -> None:
    await crud.save_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # اگر کاربر از قبل منو را دیده اما هنوز عضو کانال‌های اصلی نیست، دوباره گیت عمومی را نشان بده.
    if not await is_member(message.bot, message.from_user.id):
        missing = await get_missing_channels(message.bot, message.from_user.id, await get_join_channels())
        await message.answer(missing_join_text(JOIN_REQUIRED_TEXT, missing), reply_markup=await join_keyboard("menu", message.bot, message.from_user.id))
        return

    section_key = SECTION_BUTTON_TO_KEY.get(message.text or "")
    if section_key:
        await send_section_flow(message, section_key)


@router.callback_query(F.data.startswith("section_check:"))
async def section_check_callback(call: CallbackQuery) -> None:
    section_key = call.data.split(":", 1)[1]
    if section_key not in SECTION_TITLES:
        await call.answer("بخش نامعتبر است.", show_alert=True)
        return

    if not await is_section_member(call.bot, call.from_user.id, section_key):
        await call.answer("هنوز عضویت شما در همه کانال‌های این بخش تایید نشده است.", show_alert=True)
        try:
            missing = await get_missing_channels(call.bot, call.from_user.id, await get_section_join_channels(section_key))
            await call.message.edit_text(section_join_text(section_key, missing), reply_markup=await section_join_keyboard(section_key, call.bot, call.from_user.id))
        except Exception:
            pass
        return

    await call.answer("عضویت تایید شد ✅")
    try:
        await call.message.edit_text(SECTION_RESULT_TEXTS.get(section_key, "✅ عضویت تایید شد."))
    except Exception:
        await call.message.answer(SECTION_RESULT_TEXTS.get(section_key, "✅ عضویت تایید شد."))



@router.callback_query(F.data.startswith("link_check:"))
async def file_link_check_callback(call: CallbackQuery) -> None:
    try:
        link_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer("لینک نامعتبر است.", show_alert=True)
        return

    link_item = await crud.get_file_link(link_id)
    if link_item is None or not link_item.is_active:
        await call.answer("این لینک پیدا نشد یا غیرفعال شده است.", show_alert=True)
        return

    if not await is_file_link_member(call.bot, call.from_user.id, link_id):
        await call.answer("هنوز عضویت شما در همه کانال‌های این لینک تایید نشده است.", show_alert=True)
        try:
            missing = await get_missing_channels(call.bot, call.from_user.id, await get_file_link_join_channels(link_id))
            await call.message.edit_text(file_link_join_text(link_id, missing), reply_markup=await file_link_join_keyboard(link_id, call.bot, call.from_user.id))
        except Exception:
            pass
        return

    await call.answer("عضویت تایید شد ✅")
    try:
        await call.message.edit_text("✅ عضویت تایید شد. فایل در حال ارسال است...")
    except Exception:
        pass

    await crud.increment_file_link_views(link_id)
    await send_file_to_user(call.bot, call.message.chat.id, int(link_item.file_id))


@router.callback_query(F.data.startswith("check:"))
async def check_join_callback(call: CallbackQuery) -> None:
    payload = call.data.split(":", 1)[1]

    # بررسی عضویت عمومی برای نمایش منوی اصلی ربات
    if payload == "menu":
        if not await is_member(call.bot, call.from_user.id):
            await call.answer("هنوز عضویت شما تایید نشده است.", show_alert=True)
            try:
                missing = await get_missing_channels(call.bot, call.from_user.id, await get_join_channels())
                await call.message.edit_text(missing_join_text(JOIN_REQUIRED_TEXT, missing), reply_markup=await join_keyboard("menu", call.bot, call.from_user.id))
            except Exception:
                pass
            return

        await call.answer("عضویت تایید شد ✅")
        try:
            await call.message.delete()
        except Exception:
            pass
        if is_admin(call.from_user.id):
            await call.message.answer(ADMIN_WELCOME_TEXT, reply_markup=admin_menu())
        else:
            await call.message.answer("✅ عضویت تایید شد.\n\nاز منوی زیر انتخاب کن:", reply_markup=inline_user_menu())
        return

    file_id = extract_file_id_from_payload(payload)
    if file_id is None:
        await call.answer("لینک فایل نامعتبر است.", show_alert=True)
        return

    if not await is_member(call.bot, call.from_user.id):
        await call.answer("هنوز عضویت شما تایید نشده است.", show_alert=True)
        # دکمه‌ها را نگه می‌داریم تا کاربر بعد از عضویت دوباره بررسی کند.
        try:
            missing = await get_missing_channels(call.bot, call.from_user.id, await get_join_channels())
            await call.message.edit_text(missing_join_text(JOIN_REQUIRED_TEXT, missing), reply_markup=await join_keyboard(payload, call.bot, call.from_user.id))
        except Exception:
            pass
        return

    await call.answer("عضویت تایید شد ✅")
    try:
        await call.message.edit_text("✅ عضویت تایید شد. فایل در حال ارسال است...")
    except Exception:
        pass

    await send_file_to_user(call.bot, call.message.chat.id, file_id)


@router.message(F.text == BTN_HELP)
@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("سلام 👋\nیکی از گزینه‌های زیر را انتخاب کن:", reply_markup=inline_user_menu())
        return
    await message.answer(ADMIN_HELP_TEXT)


@router.message(F.text == BTN_STATS)
@router.message(Command("stats"))
async def stats_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    users = await crud.count_users()
    files = await crud.count_files()
    file_links = await crud.count_file_links()
    await message.answer(f"📊 آمار ربات\n\n👥 کاربران: {users}\n🎬 فایل‌ها: {files}\n🔗 لینک‌های اختصاصی: {file_links}")




def sqlite_db_path_from_url() -> Path:
    """Extract SQLite database file path from DATABASE_URL."""
    value = str(DATABASE_URL or "").strip()
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if value.startswith(prefix):
            raw_path = value[len(prefix):]
            path = Path(raw_path)
            return path if path.is_absolute() else Path.cwd() / path

    # fallback paths used in local/Railway setups
    for candidate in (Path("/app/data/bot.db"), Path("bot.db"), Path("./bot.db")):
        if candidate.exists():
            return candidate
    return Path("/app/data/bot.db")


async def send_database_backup(message: Message) -> None:
    db_path = sqlite_db_path_from_url()
    if not db_path.exists():
        await message.answer(
            "❌ فایل دیتابیس پیدا نشد.\n\n"
            f"مسیر بررسی‌شده:\n<code>{db_path}</code>\n\n"
            "اگر روی Railway هستی، مقدار DATABASE_URL باید این باشد:\n"
            "<code>sqlite+aiosqlite:////app/data/bot.db</code>"
        )
        return

    backup_name = f"movie_bot_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = Path("/tmp") / backup_name

    try:
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dest = sqlite3.connect(str(backup_path))
        with dest:
            source.backup(dest)
        source.close()
        dest.close()
    except Exception as e:
        await message.answer(f"❌ خطا هنگام ساخت بکاپ:\n<code>{e}</code>")
        return

    await message.answer_document(
        FSInputFile(str(backup_path), filename=backup_name),
        caption=(
            "💾 بکاپ دیتابیس آماده است.\n\n"
            "این فایل شامل کانال‌های اجباری، لیست فایل‌ها، وضعیت فایل‌ها و کاربران ذخیره‌شده است.\n"
            "این فایل را داخل GitHub عمومی آپلود نکن."
        ),
    )

    try:
        backup_path.unlink(missing_ok=True)
    except Exception:
        pass




@router.message(F.text == BTN_ADD_FILE)
@router.message(Command("add"))
async def add_file_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddFileState.title)
    await message.answer("عنوان فایل را بفرست:")


@router.message(AddFileState.title)
async def add_file_title(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("عنوان معتبر نیست. دوباره بفرست:")
        return
    await state.update_data(title=title)
    await state.set_state(AddFileState.forwarded_file)
    await message.answer(
        "حالا پیام فایل را از کانال خصوصی آرشیو برای من فوروارد کن.\n\n"
        "نکته: ربات باید داخل کانال آرشیو ادمین باشد."
    )


def get_forward_origin_info(message: Message) -> tuple[str | None, int | None]:
    """Return (chat_id, message_id) from a forwarded channel message."""
    origin: Any = getattr(message, "forward_origin", None)
    if origin:
        chat = getattr(origin, "chat", None)
        message_id = getattr(origin, "message_id", None)
        if chat and message_id:
            return str(chat.id), int(message_id)

    # Compatibility with older Bot API fields, if available
    chat = getattr(message, "forward_from_chat", None)
    message_id = getattr(message, "forward_from_message_id", None)
    if chat and message_id:
        return str(chat.id), int(message_id)

    return None, None


def get_telegram_file_info(message: Message) -> tuple[str | None, str | None]:
    """Extract Telegram file_id from the forwarded message.

    This is the reliable sending mode. Later we send the file using send_video,
    send_document, etc. and delete the exact returned message_id.
    """
    if message.video:
        return "video", message.video.file_id
    if message.document:
        return "document", message.document.file_id
    if message.animation:
        return "animation", message.animation.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.photo:
        # بهترین کیفیت عکس
        return "photo", message.photo[-1].file_id
    return None, None


@router.message(AddFileState.forwarded_file)
async def add_file_forwarded(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    archive_chat_id, archive_message_id = get_forward_origin_info(message)
    # روش اصلی ما telegram_file_id است. اگر تلگرام مبدا فوروارد را مخفی کرد،
    # باز هم فایل ثبت می‌شود، چون برای ارسال و حذف دقیق به file_id نیاز داریم.
    if not archive_chat_id:
        archive_chat_id = "0"
    if not archive_message_id:
        archive_message_id = 0

    if ARCHIVE_CHANNEL_ID and archive_chat_id != "0" and str(archive_chat_id) != str(ARCHIVE_CHANNEL_ID):
        await message.answer(
            "❌ این پیام از کانال آرشیو تنظیم‌شده نیست.\n\n"
            f"کانال پیام: <code>{archive_chat_id}</code>\n"
            f"کانال تنظیم‌شده: <code>{ARCHIVE_CHANNEL_ID}</code>"
        )
        return

    file_type, telegram_file_id = get_telegram_file_info(message)
    if not telegram_file_id:
        await message.answer(
            "❌ نوع فایل را نتوانستم تشخیص بدهم.\n\n"
            "لطفاً خود پیام ویدیو/فایل/عکس را از کانال آرشیو Forward کن، نه فقط متن را."
        )
        return

    data = await state.get_data()
    title = data.get("title", "بدون عنوان")
    item = await crud.add_file(
        title=title,
        archive_chat_id=archive_chat_id,
        archive_message_id=archive_message_id,
        telegram_file_id=telegram_file_id,
        file_type=file_type,
    )
    link_item = await crud.add_file_link(file_id=item.id, title=item.title)
    await state.clear()

    link = await file_link_url(message.bot, link_item.id)
    old_link = f"https://t.me/{(await message.bot.get_me()).username}?start=f_{item.id}"
    await message.answer(
        "✅ فایل ثبت شد و یک لینک اختصاصی برای آن ساخته شد.\n\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"نوع فایل: <code>{item.file_type}</code>\n"
        f"File ID: <code>{item.id}</code>\n"
        f"Link ID: <code>{link_item.id}</code>\n\n"
        f"لینک جدید با کانال‌های اختصاصی:\n<code>{link}</code>\n\n"
        f"لینک قدیمی سازگار با گیت عمومی:\n<code>{old_link}</code>\n\n"
        "حالا برای همین لینک، کانال‌های اجباری جدا تنظیم کن.",
        reply_markup=file_link_manage_kb(link_item.id, file_id=item.id, is_active=True),
    )



def file_manage_kb(file_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⛔️ غیرفعال کردن" if is_active else "✅ فعال کردن"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ ادیت عنوان", callback_data=f"fileedit:{file_id}"),
                InlineKeyboardButton(text=toggle_text, callback_data=f"filetoggle:{file_id}"),
            ],
            [
                InlineKeyboardButton(text="🔗 لینک‌های این فایل", callback_data=f"filelinks:{file_id}"),
                InlineKeyboardButton(text="➕ لینک جدید", callback_data=f"newlink:{file_id}"),
            ],
            [
                InlineKeyboardButton(text="🗑 حذف کامل", callback_data=f"filedelete:{file_id}"),
            ],
        ]
    )


async def send_file_card(message: Message, item, bot: Bot | None = None) -> None:
    bot = bot or message.bot
    me = await bot.get_me()
    status = "✅ فعال" if item.is_active else "❌ غیرفعال"
    old_link = f"https://t.me/{me.username}?start=f_{item.id}"
    links = await crud.get_file_links(file_id=item.id, active_only=True, limit=1)
    main_link = f"https://t.me/{me.username}?start=l_{links[0].id}" if links else old_link
    text = (
        f"🎬 <b>فایل #{item.id}</b>\n\n"
        f"وضعیت: {status}\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"نوع: <code>{getattr(item, 'file_type', None) or 'old'}</code>\n"
        f"بازدید: <code>{item.views}</code>\n\n"
        f"لینک اختصاصی جدید:\n<code>{main_link}</code>\n\n"
        f"لینک قدیمی:\n<code>{old_link}</code>"
    )
    await message.answer(text, reply_markup=file_manage_kb(item.id, bool(item.is_active)))


@router.message(F.text == BTN_FILES)
@router.message(Command("files"))
async def files_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    items = await crud.get_files(limit=20)
    if not items:
        await message.answer("هنوز فایلی ثبت نشده است.")
        return

    await message.answer("📋 <b>لیست فایل‌ها</b>\n\nبرای هر فایل می‌تونی ادیت، غیرفعال یا حذف کامل بزنی.")
    for item in items:
        await send_file_card(message, item)



async def send_file_links_list(message_or_call, file_id: int) -> None:
    item = await crud.get_file(file_id)
    if not item:
        text = "❌ فایل پیدا نشد."
        if isinstance(message_or_call, CallbackQuery):
            await message_or_call.answer(text, show_alert=True)
        else:
            await message_or_call.answer(text)
        return

    links = await crud.get_file_links(file_id=file_id, active_only=False, limit=50)
    me = await (message_or_call.bot.get_me() if isinstance(message_or_call, Message) else message_or_call.bot.get_me())

    lines = [f"🔗 <b>لینک‌های فایل #{file_id}</b>\nعنوان: <b>{item.title}</b>\n"]
    if not links:
        lines.append("هنوز برای این فایل لینک اختصاصی ساخته نشده است.")
    else:
        for ln in links:
            status = "✅ فعال" if ln.is_active else "❌ غیرفعال"
            url = f"https://t.me/{me.username}?start=l_{ln.id}"
            channels = await crud.get_file_link_required_channels(ln.id, active_only=True)
            lines.append(
                f"━━━━━━━━━━━━\n"
                f"{status}\n"
                f"Link ID: <code>{ln.id}</code>\n"
                f"بازدید لینک: <code>{ln.views}</code>\n"
                f"کانال‌های اجباری: <code>{len(channels)}</code>\n"
                f"<code>{url}</code>"
            )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ ساخت لینک جدید", callback_data=f"newlink:{file_id}")],
            *[
                [InlineKeyboardButton(text=f"📢 مدیریت لینک #{ln.id}", callback_data=f"linkchannels:{ln.id}")]
                for ln in links[:20]
            ],
        ]
    )

    if isinstance(message_or_call, CallbackQuery):
        await message_or_call.message.answer("\n".join(lines), reply_markup=kb)
        await message_or_call.answer()
    else:
        await message_or_call.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(F.data.startswith("filelinks:"))
async def file_links_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    file_id = int(call.data.split(":", 1)[1])
    await send_file_links_list(call, file_id)


@router.callback_query(F.data.startswith("newlink:"))
async def new_file_link_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    file_id = int(call.data.split(":", 1)[1])
    item = await crud.get_file(file_id)
    if not item:
        await call.answer("فایل پیدا نشد.", show_alert=True)
        return

    link_item = await crud.add_file_link(file_id=file_id, title=item.title)
    url = await file_link_url(call.bot, link_item.id)
    await call.message.answer(
        "✅ لینک جدید ساخته شد.\n\n"
        f"File ID: <code>{file_id}</code>\n"
        f"Link ID: <code>{link_item.id}</code>\n\n"
        f"<code>{url}</code>\n\n"
        "حالا کانال‌های اجباری همین لینک را تنظیم کن.",
        reply_markup=file_link_manage_kb(link_item.id, file_id=file_id, is_active=True),
    )
    await call.answer()


@router.callback_query(F.data.startswith("linktoggle:"))
async def file_link_toggle_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    link_id = int(call.data.split(":", 1)[1])
    link_item = await crud.get_file_link(link_id)
    if not link_item:
        await call.answer("لینک پیدا نشد.", show_alert=True)
        return

    ok = await crud.set_file_link_active(link_id, not bool(link_item.is_active))
    if not ok:
        await call.answer("خطا در تغییر وضعیت لینک.", show_alert=True)
        return
    link_item = await crud.get_file_link(link_id)
    url = await file_link_url(call.bot, link_id)
    channels = await crud.get_file_link_required_channels(link_id, active_only=True)
    status = "✅ فعال" if link_item.is_active else "❌ غیرفعال"
    await call.message.answer(
        f"🔗 لینک #{link_id}\n\n"
        f"وضعیت: {status}\n"
        f"File ID: <code>{link_item.file_id}</code>\n"
        f"کانال‌های اجباری فعال: <code>{len(channels)}</code>\n\n"
        f"<code>{url}</code>",
        reply_markup=file_link_manage_kb(link_id, file_id=link_item.file_id, is_active=bool(link_item.is_active)),
    )
    await call.answer("✅ وضعیت لینک تغییر کرد.")


@router.callback_query(F.data.startswith("linkchannels:"))
async def file_link_channels_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    link_id = int(call.data.split(":", 1)[1])
    link_item = await crud.get_file_link(link_id)
    if not link_item:
        await call.answer("لینک پیدا نشد.", show_alert=True)
        return

    channels = await crud.get_file_link_required_channels(link_id, active_only=True)
    url = await file_link_url(call.bot, link_id)
    lines = [
        f"📢 <b>کانال‌های اجباری لینک #{link_id}</b>\n",
        f"File ID: <code>{link_item.file_id}</code>",
        f"لینک:\n<code>{url}</code>\n",
    ]
    if not channels:
        lines.append("هنوز کانالی برای این لینک تنظیم نشده است.")
    else:
        for ch in channels:
            lines.append(
                f"━━━━━━━━━━━━\n"
                f"Channel ID: <code>{ch.id}</code>\n"
                f"عنوان: <b>{ch.title or '-'}</b>\n"
                f"Chat: <code>{ch.chat_id}</code>\n"
                f"Link: <code>{ch.link or '-'}</code>"
            )

    await call.message.answer(
        "\n".join(lines),
        reply_markup=file_link_manage_kb(link_id, file_id=link_item.file_id, is_active=bool(link_item.is_active)),
    )
    await call.answer()


@router.callback_query(F.data.startswith("setlinkch:"))
async def set_file_link_channels_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    link_id = int(call.data.split(":", 1)[1])
    link_item = await crud.get_file_link(link_id)
    if not link_item:
        await call.answer("لینک پیدا نشد.", show_alert=True)
        return

    await state.set_state(SetFileLinkChannelsState.channels)
    await state.update_data(link_id=link_id)
    await call.message.answer(
        f"📢 تنظیم کانال‌های اجباری برای لینک #{link_id}\n\n"
        "کانال‌ها را هرکدام در یک خط بفرست.\n\n"
        "کانال عمومی:\n"
        "<code>@YourChannel</code>\n\n"
        "کانال خصوصی:\n"
        "<code>-1001234567890 https://t.me/+InviteLink</code>\n\n"
        "اگر چند کانال داری، مثل این بفرست:\n"
        "<code>@channel1\n@channel2\n-1001234567890 https://t.me/+InviteLink</code>\n\n"
        "با ارسال لیست جدید، کانال‌های قبلی این لینک غیرفعال می‌شوند."
    )
    await call.answer()


@router.message(SetFileLinkChannelsState.channels)
async def set_file_link_channels_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    link_id = int(data.get("link_id", 0))
    link_item = await crud.get_file_link(link_id)
    if not link_item:
        await message.answer("❌ لینک پیدا نشد.")
        await state.clear()
        return

    parsed = parse_channel_lines(message.text or "")
    if not parsed:
        await message.answer("❌ هیچ کانالی تشخیص داده نشد. دوباره بفرست.")
        return

    saved = []
    errors = []

    await crud.clear_file_link_required_channels(link_id)

    for chat_id, invite_link in parsed:
        try:
            chat = await message.bot.get_chat(chat_id)
            title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
            if not invite_link and getattr(chat, "username", None):
                invite_link = f"https://t.me/{chat.username}"

            item = await crud.add_file_link_required_channel(
                link_id=link_id,
                chat_id=str(chat_id),
                link=invite_link,
                title=title,
            )
            saved.append(item)
        except Exception as e:
            errors.append(f"{chat_id} → {type(e).__name__}: {e}")

    await state.clear()

    url = await file_link_url(message.bot, link_id)
    lines = [
        "✅ تنظیم کانال‌های لینک انجام شد.\n",
        f"Link ID: <code>{link_id}</code>",
        f"File ID: <code>{link_item.file_id}</code>",
        f"لینک:\n<code>{url}</code>\n",
        f"تعداد کانال‌های ذخیره‌شده: <code>{len(saved)}</code>",
    ]
    if saved:
        lines.append("\nکانال‌های ذخیره‌شده:")
        for item in saved:
            lines.append(f"• <b>{item.title}</b> — <code>{item.chat_id}</code>")
    if errors:
        lines.append("\n❌ خطاها:")
        for err in errors:
            lines.append(f"• <code>{err}</code>")

    await message.answer(
        "\n".join(lines),
        reply_markup=file_link_manage_kb(link_id, file_id=link_item.file_id, is_active=bool(link_item.is_active)),
    )



@router.message(F.text.regexp(r"^/del\d+$"))
async def delete_file_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    file_id = int(message.text.replace("/del", ""))
    ok = await crud.set_file_active(file_id, False)
    if ok:
        await message.answer(f"✅ فایل {file_id} غیرفعال شد.")
    else:
        await message.answer("❌ فایل پیدا نشد.")


@router.callback_query(F.data.startswith("filetoggle:"))
async def file_toggle_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    file_id = int(call.data.split(":", 1)[1])
    item = await crud.get_file(file_id)
    if not item:
        await call.answer("فایل پیدا نشد.", show_alert=True)
        return

    new_status = not bool(item.is_active)
    ok = await crud.set_file_active(file_id, new_status)
    if not ok:
        await call.answer("خطا در تغییر وضعیت.", show_alert=True)
        return

    item = await crud.get_file(file_id)
    me = await call.bot.get_me()
    status = "✅ فعال" if item.is_active else "❌ غیرفعال"
    old_link = f"https://t.me/{me.username}?start=f_{item.id}"
    links = await crud.get_file_links(file_id=item.id, active_only=True, limit=1)
    main_link = f"https://t.me/{me.username}?start=l_{links[0].id}" if links else old_link
    text = (
        f"🎬 <b>فایل #{item.id}</b>\n\n"
        f"وضعیت: {status}\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"نوع: <code>{getattr(item, 'file_type', None) or 'old'}</code>\n"
        f"بازدید: <code>{item.views}</code>\n\n"
        f"لینک اختصاصی جدید:\n<code>{main_link}</code>\n\n"
        f"لینک قدیمی:\n<code>{old_link}</code>"
    )
    await call.message.edit_text(text, reply_markup=file_manage_kb(item.id, bool(item.is_active)))
    await call.answer("✅ وضعیت فایل تغییر کرد.")


@router.callback_query(F.data.startswith("filedelete:"))
async def file_delete_confirm_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    file_id = int(call.data.split(":", 1)[1])
    item = await crud.get_file(file_id)
    if not item:
        await call.answer("فایل پیدا نشد.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ بله، حذف شود", callback_data=f"filedelete_yes:{file_id}"),
                InlineKeyboardButton(text="❌ لغو", callback_data=f"filedelete_no:{file_id}"),
            ]
        ]
    )
    await call.message.answer(
        f"⚠️ مطمئنی فایل #{file_id} حذف کامل شود؟\n\n"
        f"عنوان: <b>{item.title}</b>\n\n"
        "بعد از حذف، لینک این فایل دیگر کار نمی‌کند.",
        reply_markup=kb,
    )
    await call.answer()


@router.callback_query(F.data.startswith("filedelete_no:"))
async def file_delete_cancel_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    await call.message.edit_text("❌ حذف فایل لغو شد.")
    await call.answer()


@router.callback_query(F.data.startswith("filedelete_yes:"))
async def file_delete_yes_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    file_id = int(call.data.split(":", 1)[1])
    ok = await crud.delete_file(file_id)
    if ok:
        await call.message.edit_text(f"🗑 فایل #{file_id} حذف کامل شد.")
        await call.answer("حذف شد.")
    else:
        await call.answer("فایل پیدا نشد.", show_alert=True)


@router.callback_query(F.data.startswith("fileedit:"))
async def file_edit_start_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    file_id = int(call.data.split(":", 1)[1])
    item = await crud.get_file(file_id)
    if not item:
        await call.answer("فایل پیدا نشد.", show_alert=True)
        return

    await state.set_state(EditFileState.title)
    await state.update_data(file_id=file_id)
    await call.message.answer(
        f"✏️ عنوان جدید فایل #{file_id} را بفرست:\n\n"
        f"عنوان فعلی: <b>{item.title}</b>\n\n"
        "برای لغو، /cancel بزن."
    )
    await call.answer()


@router.message(EditFileState.title)
async def file_edit_save_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    title = (message.text or "").strip()
    if not title:
        await message.answer("عنوان معتبر نیست. دوباره بفرست یا /cancel بزن.")
        return

    data = await state.get_data()
    file_id = int(data.get("file_id", 0))
    ok = await crud.update_file_title(file_id, title)
    await state.clear()

    if not ok:
        await message.answer("❌ فایل پیدا نشد.", reply_markup=admin_menu())
        return

    item = await crud.get_file(file_id)
    await message.answer("✅ عنوان فایل اصلاح شد.", reply_markup=admin_menu())
    if item:
        await send_file_card(message, item)






def extract_html_text_from_message(message: Message) -> str:
    """متن لینک‌دار تلگرام را حفظ می‌کند."""
    raw_text = (message.text or message.caption or "").strip()
    if raw_text == "/skip":
        return ""

    if message.html_text:
        return message.html_text.strip()
    if message.caption_html:
        return message.caption_html.strip()

    return raw_text


def markdown_links_to_html(text: str) -> str:
    """فرمت ساده [متن](لینک) را به HTML امن تبدیل می‌کند."""
    value = str(text or "")
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

    def repl(match: re.Match) -> str:
        label = html.escape(match.group(1), quote=False)
        url = html.escape(match.group(2), quote=True)
        return f'<a href="{url}">{label}</a>'

    return pattern.sub(repl, value)


def safe_html_preview(value: str, limit: int = 70) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    text = text.replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return html.escape(text or "بدون متن", quote=False)


# ============================================================
# لیست پست‌های منتشرشده داخل کانال‌ها
# ============================================================

def build_channel_message_link(target_channel: str, message_id: int) -> str | None:
    target = str(target_channel or "").strip()
    if not target:
        return None

    if target.startswith("@"):
        return f"https://t.me/{target.replace('@', '').strip()}/{message_id}"

    # برای کانال‌های خصوصی با آیدی -100، لینک داخلی t.me/c ساخته می‌شود.
    # این لینک فقط برای کسانی باز می‌شود که عضو همان کانال باشند.
    if target.startswith("-100") and target[4:].isdigit():
        return f"https://t.me/c/{target[4:]}/{message_id}"

    # اگر به صورت عددی بدون -100 ذخیره شد
    if target.isdigit():
        return f"https://t.me/c/{target}/{message_id}"

    return None


@router.message(F.text == BTN_POSTS)
@router.message(Command("posts"))
async def list_channel_posts_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    posts = await crud.get_channel_posts(limit=30)
    if not posts:
        await message.answer("هنوز پستی از طریق ربات داخل کانال منتشر نشده است.")
        return

    lines = ["📋 <b>آخرین پست‌های منتشرشده</b>\n"]
    for post in posts:
        title = safe_html_preview(post.post_text or "")

        link = build_channel_message_link(post.target_channel, post.message_id)
        link_line = f"🔗 <a href=\"{link}\">مشاهده پست</a>" if link else "🔗 لینک مستقیم قابل ساخت نیست"

        file_line = f"🎬 فایل: <code>{post.file_id}</code>" if post.file_id else "🎬 فایل: —"

        lines.append(
            f"━━━━━━━━━━━━\n"
            f"ID: <code>{post.id}</code>\n"
            f"کانال: <code>{post.target_channel}</code>\n"
            f"Message ID: <code>{post.message_id}</code>\n"
            f"{file_line}\n"
            f"دکمه: <b>{post.button_text or '—'}</b>\n"
            f"متن: {title}\n"
            f"{link_line}"
        )

    await message.answer("\n".join(lines), disable_web_page_preview=True)


# ============================================================
# ساخت پست دکمه‌دار برای کانال اصلی
# ============================================================

def normalize_post_button_url(raw: str, bot_username: str) -> str | None:
    value = str(raw or "").strip()

    if not value:
        return None

    # اگر ادمین فقط عدد فرستاد، برای سازگاری قدیمی آن را File ID فرض می‌کنیم: f_12
    if value.isdigit():
        return f"https://t.me/{bot_username}?start=f_{value}"

    # لینک جدید اختصاصی: l_101
    if value.startswith("l_") and value[2:].isdigit():
        return f"https://t.me/{bot_username}?start={value}"

    if value.startswith("/start=l_"):
        payload = value.split("=", 1)[1]
        return f"https://t.me/{bot_username}?start={payload}"

    # لینک قدیمی: f_12
    if value.startswith("f_") and value[2:].isdigit():
        return f"https://t.me/{bot_username}?start={value}"

    if value.startswith("/start=f_"):
        payload = value.split("=", 1)[1]
        return f"https://t.me/{bot_username}?start={payload}"

    # اگر لینک کامل بود
    if value.startswith("https://") or value.startswith("http://") or value.startswith("tg://"):
        return value

    # اگر @username بود، لینک تلگرام بساز
    if value.startswith("@"):
        return f"https://t.me/{value.replace('@', '').strip()}"

    # اگر دامنه بدون https فرستاد
    if "." in value and " " not in value:
        return "https://" + value

    return None


def normalize_button_style(raw: str | None) -> str | None:
    value = str(raw or "").strip().lower()

    if value in {"", "none", "default", "معمولی", "ساده", "خالی", "بدون"}:
        return None

    if value in {"green", "success", "سبز", "🟢"}:
        return "success"

    if value in {"red", "danger", "قرمز", "سرخ", "🔴", "خطر"}:
        return "danger"

    if value in {"blue", "primary", "آبی", "ابی", "🔵"}:
        return "primary"

    # رنگ‌های آزاد مثل طلایی/بنفش در Bot API رسمی وجود ندارند.
    return None


def make_url_button(text: str, url: str, style: str | None = None, custom_emoji_id: str | None = None) -> InlineKeyboardButton:
    data: dict[str, Any] = {
        "text": text,
        "url": url,
    }

    if style:
        data["style"] = style

    if custom_emoji_id:
        data["icon_custom_emoji_id"] = custom_emoji_id

    try:
        # aiogram نسخه‌های جدید/قدیمی معمولاً extra_data را می‌پذیرند.
        return InlineKeyboardButton(**data)
    except TypeError:
        # اگر کتابخانه style را نشناخت، دکمه معمولی ساخته می‌شود.
        return InlineKeyboardButton(text=text, url=url)


def custom_post_buttons_kb(buttons: list[dict[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for btn in buttons[:10]:
        text = str(btn.get("text") or "باز کردن لینک")
        url = str(btn.get("url") or "")
        style = normalize_button_style(btn.get("style"))
        custom_emoji_id = (btn.get("custom_emoji_id") or "").strip() or None

        rows.append([make_url_button(text=text, url=url, style=style, custom_emoji_id=custom_emoji_id)])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_post_buttons(raw: str, bot_username: str, suggested_link: str = "") -> tuple[list[dict[str, str]], list[str]]:
    """Parse up to 10 button lines.

    هر خط:
    متن دکمه | لینک | رنگ

    رنگ اختیاری است:
    سبز/success، قرمز/danger، آبی/primary، معمولی/default
    """
    value = str(raw or "").strip()
    errors: list[str] = []
    buttons: list[dict[str, str]] = []

    if value == "/skip":
        if suggested_link:
            return [{"text": "🎬 دریافت فایل", "url": suggested_link, "style": "success"}], []
        return [], ["برای /skip باید اول فایل ثبت‌شده انتخاب شده باشد یا لینک پیشنهادی وجود داشته باشد."]

    lines = [ln.strip() for ln in value.splitlines() if ln.strip()]
    if len(lines) > 10:
        errors.append("حداکثر ۱۰ دکمه مجاز است؛ فقط ۱۰ خط اول بررسی شد.")
        lines = lines[:10]

    for idx, line in enumerate(lines, start=1):
        parts = [p.strip() for p in line.split("|")]

        if len(parts) < 2:
            errors.append(f"خط {idx}: فرمت درست نیست. نمونه: متن دکمه | لینک | سبز")
            continue

        text = parts[0]
        raw_link = parts[1]
        style = normalize_button_style(parts[2] if len(parts) >= 3 else None)

        if not text:
            errors.append(f"خط {idx}: متن دکمه خالی است.")
            continue

        if len(text) > 80:
            errors.append(f"خط {idx}: متن دکمه خیلی طولانی است.")
            continue

        if raw_link == "/skip" and suggested_link:
            url = suggested_link
        else:
            url = normalize_post_button_url(raw_link, bot_username)

        if not url:
            errors.append(f"خط {idx}: لینک معتبر نیست.")
            continue

        buttons.append({
            "text": text,
            "url": url,
            "style": style or "",
        })

    if not buttons:
        errors.append("هیچ دکمه معتبری ساخته نشد.")

    return buttons, errors



def choose_post_file_kb(items) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        status = "✅" if item.is_active else "❌"
        title = str(item.title or "بدون عنوان")
        if len(title) > 32:
            title = title[:29] + "..."
        rows.append([InlineKeyboardButton(text=f"{status} #{item.id} — {title}", callback_data=f"postfile:{item.id}")])
    rows.append([InlineKeyboardButton(text="⏭ بدون انتخاب فایل ثبت‌شده", callback_data="postfile:none")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def parse_target_channels(raw: str) -> list[str]:
    value = str(raw or "").strip()

    if value == "/default":
        return [POST_CHANNEL_ID] if POST_CHANNEL_ID else []

    # جدا کردن با خط جدید، فاصله یا کاما
    parts = re.split(r"[\s,]+", value)
    channels: list[str] = []
    for part in parts:
        ch = part.strip()
        if not ch:
            continue
        # لینک t.me را تبدیل به @username می‌کنیم
        if ch.startswith("https://t.me/") or ch.startswith("http://t.me/"):
            name = ch.rstrip("/").split("/")[-1]
            if name and not name.startswith("+") and name != "c":
                ch = "@" + name
        channels.append(ch)

    return channels

def post_button_color_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 سبز", callback_data="pbc:success"),
                InlineKeyboardButton(text="🔴 قرمز", callback_data="pbc:danger"),
            ],
            [
                InlineKeyboardButton(text="🔵 آبی", callback_data="pbc:primary"),
                InlineKeyboardButton(text="⚪ معمولی", callback_data="pbc:"),
            ],
        ]
    )


def post_buttons_next_kb(buttons_count: int) -> InlineKeyboardMarkup:
    rows = []
    if buttons_count < 10:
        rows.append([InlineKeyboardButton(text="➕ افزودن دکمه دیگر", callback_data="pbnext:add")])
    rows.append([InlineKeyboardButton(text=f"✅ پایان دکمه‌ها ({buttons_count})", callback_data="pbnext:finish")])
    rows.append([InlineKeyboardButton(text="🧹 پاک کردن همه دکمه‌ها", callback_data="pbnext:clear")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buttons_preview_text(buttons: list[dict[str, str]]) -> str:
    if not buttons:
        return "هنوز دکمه‌ای اضافه نشده است."
    lines = []
    for i, btn in enumerate(buttons, start=1):
        style = btn.get("style") or "معمولی"
        lines.append(f"{i}. {btn.get('text', 'دکمه')} — {style}")
    return "\n".join(lines)


async def ask_button_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    buttons = data.get("buttons", []) or []
    suggested_link = data.get("suggested_link", "")

    if len(buttons) >= 10:
        await ask_target_channels_after_step_buttons(message, state)
        return

    extra = ""
    if suggested_link and not buttons:
        extra = "\n\nاگر می‌خوای یک دکمه پیش‌فرض «🔥 دریافت فایل 🔥» با لینک فایل ساخته شود، /skip بزن."

    await state.update_data(button_step="text", pending_button=None)
    await message.answer(
        f"حالا متن دکمه شیشه‌ای را بفرست.\n\n"
        f"دکمه‌های ساخته‌شده: <code>{len(buttons)}</code> از <code>10</code>\n\n"
        "مثال:\n"
        "<code>🔥 دریافت فایل 🔥</code>\n"
        "<code>📣 ورود به کانال</code>\n"
        "<code>💎 مشاهده سایت</code>"
        f"{extra}"
    )


async def ask_target_channels_after_step_buttons(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    buttons = data.get("buttons", []) or []

    if not buttons:
        await message.answer("❌ هنوز هیچ دکمه‌ای نساختی. اول حداقل یک دکمه اضافه کن.")
        await ask_button_text(message, state)
        return

    await state.set_state(CreateChannelPostState.target_channels)

    default_text = ""
    if POST_CHANNEL_ID:
        default_text = (
            "\n\nاگر می‌خوای به کانال پیش‌فرض Railway ارسال شود، /default بزن.\n"
            f"کانال پیش‌فرض: <code>{POST_CHANNEL_ID}</code>"
        )

    await message.answer(
        "✅ دکمه‌ها آماده شدند:\n"
        + buttons_preview_text(buttons)
        + "\n\nحالا کانال مقصد انتشار پست را بفرست.\n\n"
        "مثال برای یک کانال:\n"
        "<code>@YourChannel</code>\n\n"
        "مثال برای چند کانال:\n"
        "<code>@Channel1 @Channel2 -1001234567890</code>"
        f"{default_text}\n\n"
        "نکته: ربات باید داخل همه این کانال‌ها ادمین باشد و اجازه ارسال پست داشته باشد."
    )



async def publish_channel_post(
    bot: Bot,
    target_channels: list[str],
    post_text: str,
    media_type: str | None,
    media_file_id: str | None,
    buttons: list[dict[str, str]],
    media_has_spoiler: bool = False,
) -> tuple[list[tuple[str, int]], list[str]]:
    if not target_channels:
        raise RuntimeError("target channel is not set")

    if not buttons:
        raise RuntimeError("buttons are not set")

    text = (post_text or "").strip()
    if not text:
        text = "برای ادامه روی دکمه زیر بزن."

    reply_markup = custom_post_buttons_kb(buttons)

    if media_file_id and len(text) > 1000:
        raise RuntimeError("caption_too_long")

    sent_to: list[tuple[str, int]] = []
    failed: list[str] = []

    for target in target_channels:
        try:
            if not media_file_id:
                sent = await bot.send_message(
                    chat_id=target,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            elif media_type == "photo":
                sent = await bot.send_photo(chat_id=target, photo=media_file_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, has_spoiler=media_has_spoiler)
            elif media_type == "video":
                sent = await bot.send_video(chat_id=target, video=media_file_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, has_spoiler=media_has_spoiler)
            elif media_type == "animation":
                sent = await bot.send_animation(chat_id=target, animation=media_file_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, has_spoiler=media_has_spoiler)
            elif media_type == "document":
                sent = await bot.send_document(chat_id=target, document=media_file_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            else:
                sent = await bot.send_message(
                    chat_id=target,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            sent_to.append((target, sent.message_id))
        except Exception as e:
            failed.append(f"{target} → {e}")

    return sent_to, failed


@router.message(F.text == BTN_CREATE_CHANNEL_POST)
@router.message(Command("post"))
async def create_channel_post_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    await state.clear()

    # اگر POST_CHANNEL_ID تنظیم نشده باشد هم مشکلی نیست؛
    # در مرحله آخر ادمین کانال مقصد را دستی وارد می‌کند.

    items = await crud.get_files(limit=30)
    if items:
        await message.answer(
            "📤 <b>ساخت پست کانال</b>\n\n"
            "اگر می‌خواهی لینک دکمه به یکی از فایل‌های ثبت‌شده وصل شود، فایل را انتخاب کن.\n\n"
            "اگر می‌خواهی بعداً لینک دلخواه بدهی، گزینه «بدون انتخاب فایل ثبت‌شده» را بزن.",
            reply_markup=choose_post_file_kb(items),
        )
    else:
        await state.set_state(CreateChannelPostState.text)
        await state.update_data(file_id=None, suggested_link="")
        await message.answer(
            "📤 <b>ساخت پست کانال</b>\n\n"
            "هنوز فایل ثبت‌شده‌ای نداری. مشکلی نیست؛ بعداً لینک دلخواه را می‌گیریم.\n\n"
            "حالا متن پست کانال را بفرست.\n"
            "اگر متن نمی‌خوای، /skip بزن.\n"
            "برای لغو، /cancel بزن."
        )


@router.callback_query(F.data.startswith("postfile:"))
async def create_channel_post_choose_file(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    selected = call.data.split(":", 1)[1]
    suggested_link = ""

    if selected == "none":
        file_id = None
        file_title = "بدون فایل ثبت‌شده"
    else:
        file_id = int(selected)
        item = await crud.get_file(file_id)
        if not item:
            await call.answer("فایل پیدا نشد.", show_alert=True)
            return
        me = await call.bot.get_me()
        links = await crud.get_file_links(file_id=file_id, active_only=True, limit=1)
        if links:
            suggested_link = f"https://t.me/{me.username}?start=l_{links[0].id}"
        else:
            suggested_link = f"https://t.me/{me.username}?start=f_{file_id}"
        file_title = item.title

    await state.set_state(CreateChannelPostState.text)
    await state.update_data(file_id=file_id, suggested_link=suggested_link)
    await call.message.answer(
        f"✅ انتخاب شد: <b>{file_title}</b>\n\n"
        "حالا متن پست کانال را بفرست.\n\n"
        "اگر متن نمی‌خوای، /skip بزن.\n"
        "برای لغو، /cancel بزن."
    )
    await call.answer()


@router.message(CreateChannelPostState.text)
async def create_channel_post_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    text = extract_html_text_from_message(message)
    text = markdown_links_to_html(text)
    if len(text) > 4090:
        await message.answer("متن خیلی طولانیه. لطفاً کوتاه‌تر بفرست.")
        return

    await state.update_data(post_text=text)
    await state.set_state(CreateChannelPostState.media)
    await message.answer(
        "حالا عکس، ویدیو، گیف یا فایل پست را بفرست.\n\n"
        "اگر پست فقط متنی باشد، /skip بزن.\n"
        "برای لغو، /cancel بزن."
    )


@router.message(CreateChannelPostState.media)
async def create_channel_post_media(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    media_type: str | None = None
    media_file_id: str | None = None
    media_has_spoiler = False

    if (message.text or "").strip() != "/skip":
        media_type, media_file_id = get_telegram_file_info(message)
        if not media_file_id:
            await message.answer(
                "نوع مدیا را تشخیص ندادم.\n\n"
                "یک عکس، ویدیو، گیف یا فایل بفرست؛ یا برای پست متنی /skip بزن.\n\nاگر عکس/ویدیو/گیف را با Hide with spoiler بفرستی، ربات همان حالت اسپویلر را داخل کانال حفظ می‌کند."
            )
            return

        media_has_spoiler = bool(getattr(message, "has_media_spoiler", False))

    await state.update_data(
        media_type=media_type,
        media_file_id=media_file_id,
        media_has_spoiler=media_has_spoiler,
        buttons=[],
        pending_button=None,
        button_step="text",
    )
    await state.set_state(CreateChannelPostState.buttons)
    await ask_button_text(message, state)


@router.message(CreateChannelPostState.buttons)
async def create_channel_post_button_step(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    step = data.get("button_step", "text")
    buttons = data.get("buttons", []) or []

    if len(buttons) >= 10:
        await ask_target_channels_after_step_buttons(message, state)
        return

    raw = (message.text or "").strip()

    if step == "text":
        suggested_link = data.get("suggested_link", "")

        if raw == "/skip":
            if suggested_link and not buttons:
                await state.update_data(pending_button={"text": "🔥 دریافت فایل 🔥", "url": suggested_link}, button_step="color")
                await message.answer(
                    "رنگ دکمه را انتخاب کن:\n\n"
                    "متن: <b>🔥 دریافت فایل 🔥</b>\n"
                    f"لینک: <code>{suggested_link}</code>",
                    reply_markup=post_button_color_kb(),
                )
                return

            await message.answer("برای /skip باید اول فایل ثبت‌شده انتخاب شده باشد.")
            return

        if not raw:
            await message.answer("متن دکمه خالی است. دوباره بفرست.")
            return

        if len(raw) > 80:
            await message.answer("متن دکمه خیلی طولانیه. کوتاه‌تر بفرست.")
            return

        await state.update_data(pending_button={"text": raw}, button_step="link")
        await message.answer(
            "حالا لینک همین دکمه را بفرست.\n\n"
            f"متن دکمه: <b>{raw}</b>\n\n"
            "مثال:\n"
            "<code>https://t.me/YourChannel</code>\n"
            "<code>https://example.com</code>\n"
            "<code>l_5</code>"
        )
        return

    if step == "link":
        pending = data.get("pending_button") or {}
        if not pending.get("text"):
            await ask_button_text(message, state)
            return

        if raw == "/skip" and data.get("suggested_link"):
            button_url = data["suggested_link"]
        else:
            me = await message.bot.get_me()
            button_url = normalize_post_button_url(raw, me.username)

        if not button_url:
            await message.answer(
                "لینک معتبر نیست.\n\n"
                "لینک کامل بفرست، مثلا:\n"
                "<code>https://t.me/YourChannel</code>\n"
                "یا:\n"
                "<code>https://example.com</code>"
            )
            return

        pending["url"] = button_url
        await state.update_data(pending_button=pending, button_step="color")
        await message.answer(
            "رنگ دکمه را انتخاب کن:\n\n"
            f"متن: <b>{pending['text']}</b>\n"
            f"لینک: <code>{button_url}</code>",
            reply_markup=post_button_color_kb(),
        )
        return

    await ask_button_text(message, state)


@router.callback_query(CreateChannelPostState.buttons, F.data.startswith("pbc:"))
async def create_channel_post_button_color(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    data = await state.get_data()
    pending = data.get("pending_button") or {}
    buttons = data.get("buttons", []) or []

    if not pending.get("text") or not pending.get("url"):
        await call.answer("دکمه ناقص است.", show_alert=True)
        await ask_button_text(call.message, state)
        return

    if len(buttons) >= 10:
        await call.answer("حداکثر ۱۰ دکمه مجاز است.", show_alert=True)
        return

    style = call.data.split(":", 1)[1]
    buttons.append({
        "text": pending["text"],
        "url": pending["url"],
        "style": normalize_button_style(style) or "",
    })

    await state.update_data(buttons=buttons, pending_button=None, button_step="next")

    await call.message.answer(
        "✅ دکمه اضافه شد.\n\n"
        "دکمه‌های فعلی:\n"
        + buttons_preview_text(buttons)
        + "\n\nمی‌خوای دکمه دیگری اضافه کنی؟",
        reply_markup=post_buttons_next_kb(len(buttons)),
    )
    await call.answer()


@router.callback_query(CreateChannelPostState.buttons, F.data.startswith("pbnext:"))
async def create_channel_post_button_next(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    action = call.data.split(":", 1)[1]
    data = await state.get_data()
    buttons = data.get("buttons", []) or []

    if action == "add":
        if len(buttons) >= 10:
            await call.answer("حداکثر ۱۰ دکمه مجاز است.", show_alert=True)
            return
        await ask_button_text(call.message, state)
        await call.answer()
        return

    if action == "clear":
        await state.update_data(buttons=[], pending_button=None, button_step="text")
        await call.message.answer("🧹 همه دکمه‌های این پست پاک شد.")
        await ask_button_text(call.message, state)
        await call.answer()
        return

    if action == "finish":
        await ask_target_channels_after_step_buttons(call.message, state)
        await call.answer()
        return

    await call.answer("گزینه نامعتبر است.", show_alert=True)



@router.message(CreateChannelPostState.target_channels)
async def create_channel_post_target_channels(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    raw_targets = (message.text or "").strip()
    target_channels = parse_target_channels(raw_targets)

    if not target_channels:
        await message.answer(
            "کانال مقصد معتبر نیست.\n\n"
            "مثال:\n"
            "<code>@YourChannel</code>\n\n"
            "یا اگر POST_CHANNEL_ID در Railway تنظیم شده، /default بزن."
        )
        return

    try:
        buttons = data.get("buttons", [])
        sent_to, failed = await publish_channel_post(
            bot=message.bot,
            target_channels=target_channels,
            post_text=data.get("post_text", ""),
            media_type=data.get("media_type"),
            media_file_id=data.get("media_file_id"),
            buttons=buttons,
            media_has_spoiler=bool(data.get("media_has_spoiler", False)),
        )

        button_text_summary = " | ".join(str(btn.get("text", "")) for btn in buttons)[:240] if buttons else "—"
        button_url_summary = str(buttons[0].get("url", "")) if buttons else ""

        for target, msg_id in sent_to:
            await crud.add_channel_post(
                target_channel=target,
                message_id=msg_id,
                file_id=data.get("file_id"),
                post_text=data.get("post_text", ""),
                button_text=button_text_summary,
                button_url=button_url_summary,
                media_type=data.get("media_type"),
            )
    except RuntimeError as e:
        if str(e) == "caption_too_long":
            await message.answer(
                "متن پست برای کپشن عکس/ویدیو طولانی است.\n\n"
                "متن را کوتاه‌تر کن یا /cancel بزن و دوباره پست متنی بساز."
            )
            return
        await message.answer(f"❌ خطا در ارسال پست:\n<code>{e}</code>")
        await state.clear()
        return
    except Exception as e:
        await message.answer(
            "❌ خطا در ارسال پست به کانال.\n\n"
            "این موارد را چک کن:\n"
            "1. کانال مقصد درست باشد.\n"
            "2. ربات داخل کانال ادمین باشد.\n"
            "3. ربات اجازه ارسال پست داشته باشد.\n"
            "4. لینک دکمه معتبر باشد.\n\n"
            f"Error: <code>{e}</code>"
        )
        await state.clear()
        return

    await state.clear()

    msg = "✅ ارسال پست تمام شد.\n\n"
    if sent_to:
        msg += "ارسال موفق به:\n" + "\n".join(f"• <code>{target}</code> — پیام <code>{msg_id}</code>" for target, msg_id in sent_to)
    if failed:
        msg += "\n\n❌ خطا در این کانال‌ها:\n" + "\n".join(f"• <code>{x}</code>" for x in failed)

    await message.answer(msg, reply_markup=admin_menu())




# دستورهای قدیمی روش قبلی؛ دیگر اجرا نمی‌شوند تا ادمین فقط از پنل جدید استفاده کند.
@router.message(Command("addsectionchannel"))
@router.message(Command("delsectionchannel"))
@router.message(Command("clearsection"))
@router.message(Command("debug_section"))
@router.message(Command("addvpnchannel"))
@router.message(Command("addaccountchannel"))
@router.message(Command("addtelegramchannel"))
@router.message(Command("addcontactchannel"))
@router.message(Command("sectionchannels"))
@router.message(Command("setchannel"))
@router.message(Command("delchannel"))
async def old_channel_commands_disabled(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "این دستور مربوط به روش قبلی بود و دیگر استفاده نمی‌شود.\n\n"
        "برای مدیریت کانال‌ها از این مسیر استفاده کن:\n"
        "📢 کانال‌های اجباری → انتخاب بخش → افزودن، ادیت یا حذف کانال",
        reply_markup=admin_menu(),
    )


@router.message(F.text == BTN_ADD_REQUIRED_CHANNEL)
@router.message(Command("addchannelmenu"))
async def add_required_channel_menu_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await send_channel_manager_root(message)


@router.callback_query(F.data.startswith("addgate:"))
async def add_required_channel_target_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    target = call.data.split(":", 1)[1]
    if target == "contact":
        await call.answer("ارتباط با تیم ما عضویت اجباری جداگانه ندارد.", show_alert=True)
        return
    if target != "main" and target not in SECTION_TITLES:
        await call.answer("بخش نامعتبر است.", show_alert=True)
        return

    await state.set_state(AddSectionChannelState.channel)
    if target == "main":
        await state.update_data(target_type="main")
        title = "عضویت اجباری شروع ربات"
    else:
        await state.update_data(target_type="section", section_key=target)
        title = SECTION_TITLES.get(target, target)

    await call.message.answer(
        f"✅ بخش انتخاب شد: <b>{title}</b>\n\n"
        "حالا فقط یوزرنیم کانالی را بفرست که می‌خوای عضویت اجباری برای آن فعال شود.\n\n"
        "نمونه کانال عمومی:\n"
        "<code>@YourChannel</code>\n\n"
        "اگر کانال خصوصی است، این مدل را بفرست:\n"
        "<code>-1001234567890 https://t.me/+InviteLink</code>"
    )
    await call.answer()


@router.message(F.text.in_({BTN_CHANNELS, BTN_SECTION_CHANNELS}))
@router.message(Command("channels"))
@router.message(Command("sectionchannels"))
async def channels_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await send_channel_manager_root(message)


async def _validate_and_save_channel(bot: Bot, chat_id: str, link: str | None, replace_all: bool = False):
    chat = await bot.get_chat(chat_id)
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)

    if not link and getattr(chat, "username", None):
        link = f"https://t.me/{chat.username}"

    if replace_all:
        await crud.clear_required_channels()

    return await crud.add_required_channel(
        chat_id=str(chat_id),
        link=link,
        title=title,
    )


@router.message(Command("addchannel"))
async def add_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "این دستور خالی اجرا نمی‌شود و هیچ کانالی اضافه نشد.\n\n"
            "اول انتخاب کن این کانال برای کدام بخش عضویت اجباری شود:",
            reply_markup=add_required_channel_target_kb(),
        )
        return

    chat_id = parts[1].strip()
    link = parts[2].strip() if len(parts) >= 3 else None

    try:
        item = await _validate_and_save_channel(message.bot, chat_id=chat_id, link=link, replace_all=False)
    except Exception as e:
        await message.answer(
            "❌ کانال اضافه نشد.\n\n"
            "ربات باید داخل آن کانال ادمین باشد و مقدار کانال درست باشد.\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return

    await message.answer(
        "✅ کانال اجباری اضافه شد.\n\n"
        f"ID: <code>{item.id}</code>\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>"
    )


@router.message(Command("setchannel"))
async def set_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "فرمت درست:\n"
            "<code>/setchannel @irfreenet</code>\n\n"
            "این دستور همه کانال‌های قبلی را غیرفعال می‌کند و فقط همین کانال را فعال می‌گذارد."
        )
        return

    chat_id = parts[1].strip()
    link = parts[2].strip() if len(parts) >= 3 else None

    try:
        item = await _validate_and_save_channel(message.bot, chat_id=chat_id, link=link, replace_all=True)
    except Exception as e:
        await message.answer(
            "❌ کانال جایگزین نشد.\n\n"
            "ربات باید داخل آن کانال ادمین باشد و مقدار کانال درست باشد.\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return

    await message.answer(
        "✅ کانال اجباری جایگزین شد.\n\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>"
    )


@router.message(F.text.regexp(r"^/delchannel\d+$"))
@router.message(Command("delchannel"))
async def delete_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    text = message.text or ""
    if text.startswith("/delchannel") and text.replace("/delchannel", "").isdigit():
        channel_id = int(text.replace("/delchannel", ""))
    else:
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await message.answer(
                "فرمت درست:\n"
                "<code>/delchannel 1</code>\n\n"
                "ID کانال را از بخش /channels بردار."
            )
            return
        channel_id = int(parts[1].strip())

    ok = await crud.disable_required_channel(channel_id)
    if ok:
        await message.answer(f"✅ کانال اجباری {channel_id} غیرفعال شد.")
    else:
        await message.answer("❌ کانال پیدا نشد.")


@router.callback_query(F.data == "manageback")
async def manage_channels_back_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    await send_channel_manager_root(call)


@router.callback_query(F.data == "manageaddmenu")
async def manage_add_menu_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    try:
        await call.message.edit_text(
            "➕ می‌خوای عضویت اجباری برای کدام بخش اضافه شود؟\n\n"
            "بخش را انتخاب کن، بعد فقط یوزرنیم کانال را بفرست.",
            reply_markup=add_required_channel_target_kb(),
        )
    except Exception:
        await call.message.answer(
            "➕ می‌خوای عضویت اجباری برای کدام بخش اضافه شود؟",
            reply_markup=add_required_channel_target_kb(),
        )
    await call.answer()


@router.callback_query(F.data.startswith("managegate:"))
async def manage_channel_target_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    target = call.data.split(":", 1)[1]
    await send_channel_target_list(call, target)


@router.callback_query(F.data.startswith("manageadd:"))
async def manage_channel_add_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    target = call.data.split(":", 1)[1]
    if target not in CHANNEL_MANAGER_TARGETS:
        await call.answer("بخش نامعتبر است.", show_alert=True)
        return
    await state.set_state(AddSectionChannelState.channel)
    if target == "main":
        await state.update_data(target_type="main")
    else:
        await state.update_data(target_type="section", section_key=target)
    await call.message.answer(
        f"➕ افزودن کانال برای <b>{CHANNEL_MANAGER_TARGETS[target]}</b>\n\n"
        "حالا فقط یوزرنیم کانال را بفرست. نمونه:\n"
        "<code>@YourChannel</code>\n\n"
        "اگر کانال خصوصی است، این مدل را بفرست:\n"
        "<code>-1001234567890 https://t.me/+InviteLink</code>"
    )
    await call.answer()


@router.callback_query(F.data.startswith("managedel:"))
async def manage_channel_delete_callback(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    try:
        _, target, raw_id = call.data.split(":", 2)
        channel_id = int(raw_id)
    except Exception:
        await call.answer("درخواست نامعتبر است.", show_alert=True)
        return
    if target == "main":
        ok = await crud.disable_required_channel(channel_id)
    else:
        ok = await crud.disable_section_required_channel(channel_id)
    if not ok:
        await call.answer("کانال پیدا نشد.", show_alert=True)
        return
    await call.answer("کانال حذف شد ✅", show_alert=True)
    await send_channel_target_list(call, target)


@router.callback_query(F.data.startswith("manageedit:"))
async def manage_channel_edit_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return
    try:
        _, target, raw_id = call.data.split(":", 2)
        channel_id = int(raw_id)
    except Exception:
        await call.answer("درخواست نامعتبر است.", show_alert=True)
        return
    if target not in CHANNEL_MANAGER_TARGETS:
        await call.answer("بخش نامعتبر است.", show_alert=True)
        return
    await state.set_state(AddSectionChannelState.channel)
    if target == "main":
        await state.update_data(target_type="edit_main", edit_id=channel_id)
    else:
        await state.update_data(target_type="edit_section", section_key=target, edit_id=channel_id)
    await call.message.answer(
        f"✏️ ادیت کانال بخش <b>{CHANNEL_MANAGER_TARGETS[target]}</b>\n\n"
        "یوزرنیم یا آیدی جدید کانال را بفرست. نمونه:\n"
        "<code>@NewChannel</code>\n\n"
        "برای کانال خصوصی:\n"
        "<code>-1001234567890 https://t.me/+InviteLink</code>"
    )
    await call.answer()


@router.callback_query(F.data.startswith("noop:"))
async def noop_callback(call: CallbackQuery) -> None:
    await call.answer()


@router.message(F.text == BTN_SECTION_CHANNELS)
@router.message(Command("sectionchannels"))
async def section_channels_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    channels = await crud.get_section_required_channels(active_only=False)
    lines = ["🧩 <b>کانال‌های عضویت اختصاصی بخش‌ها</b>\n"]
    lines.append("کلیدهای مجاز: <code>telegram</code>، <code>vpn</code>، <code>accounts</code>\n")

    if channels:
        for ch in channels:
            status = "✅ فعال" if ch.is_active else "❌ غیرفعال"
            section_title = SECTION_TITLES.get(ch.section_key, ch.section_key)
            lines.append(
                f"{status}\n"
                f"ID: <code>{ch.id}</code>\n"
                f"بخش: <b>{section_title}</b> — <code>{ch.section_key}</code>\n"
                f"عنوان: <b>{ch.title or '-'}</b>\n"
                f"Chat: <code>{ch.chat_id}</code>\n"
                f"Link: <code>{ch.link or '-'}</code>\n"
                f"حذف: <code>/delsectionchannel {ch.id}</code>\n"
            )
    else:
        lines.append("هنوز کانال اختصاصی برای دکمه‌های کاربر ثبت نشده است.\n")

    lines.append(
        "\n<b>نمونه دستورها:</b>\n"
        "<code>/addsectionchannel vpn @channel1</code>\n"
        "<code>/addsectionchannel vpn @channel2</code>\n"
        "<code>/addsectionchannel accounts @channel3</code>\n"
        "<code>/addsectionchannel telegram @channel4</code>\n"
        "<code>/addsectionchannel contact @channel5</code>\n\n"
        "کانال خصوصی:\n"
        "<code>/addsectionchannel vpn -1001234567890 https://t.me/+InviteLink</code>\n\n"
        "حذف همه کانال‌های یک بخش:\n"
        "<code>/clearsection vpn</code>\n\n"
        "تست دسترسی:\n"
        "<code>/debug_section vpn</code>"
    )
    await message.answer("\n".join(lines))


async def _validate_and_save_section_channel(bot: Bot, section_key: str, chat_id: str, link: str | None = None):
    if section_key not in SECTION_TITLES:
        raise ValueError(f"section_key نامعتبر است. مقدارهای مجاز: {SECTION_KEY_HELP}")

    chat = await bot.get_chat(chat_id)
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)

    if not link and getattr(chat, "username", None):
        link = f"https://t.me/{chat.username}"

    return await crud.add_section_required_channel(
        section_key=section_key,
        chat_id=str(chat_id),
        link=link,
        title=title,
    )


@router.message(Command("addsectionchannel"))
async def add_section_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(
            "فرمت درست:\n"
            "<code>/addsectionchannel vpn @YourChannel</code>\n\n"
            "کلیدهای مجاز:\n"
            f"<code>{SECTION_KEY_HELP}</code>\n\n"
            "برای کانال خصوصی:\n"
            "<code>/addsectionchannel vpn -1001234567890 https://t.me/+InviteLink</code>"
        )
        return

    section_key = parts[1].strip()
    chat_id = parts[2].strip()
    link = parts[3].strip() if len(parts) >= 4 else None

    try:
        item = await _validate_and_save_section_channel(message.bot, section_key=section_key, chat_id=chat_id, link=link)
    except Exception as e:
        await message.answer(
            "❌ کانال اختصاصی اضافه نشد.\n\n"
            "ربات باید داخل آن کانال ادمین باشد و مقدار کانال درست باشد.\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return

    await message.answer(
        "✅ کانال اختصاصی بخش اضافه شد.\n\n"
        f"ID: <code>{item.id}</code>\n"
        f"بخش: <b>{SECTION_TITLES.get(item.section_key, item.section_key)}</b>\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>"
    )




async def _save_main_required_channel(message: Message, channel_text: str) -> None:
    """Save a general /start forced-join channel from a plain @username or private channel id + invite link."""
    raw = (channel_text or "").strip()
    if not raw:
        await message.answer("❌ اسم کانال خالی است. مثلا بنویس: <code>@YourChannel</code>")
        return

    parts = raw.split(maxsplit=1)
    chat_id = parts[0].strip()
    link = parts[1].strip() if len(parts) > 1 else None

    try:
        item = await _validate_and_save_channel(message.bot, chat_id=chat_id, link=link, replace_all=False)
    except Exception as e:
        await message.answer(
            "❌ کانال اصلی اضافه نشد.\n\n"
            "ربات باید داخل آن کانال ادمین باشد و مقدار کانال درست باشد.\n"
            "برای کانال عمومی نمونه: <code>@YourChannel</code>\n"
            "برای کانال خصوصی نمونه: <code>-1001234567890 https://t.me/+InviteLink</code>\n\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return

    await message.answer(
        "✅ کانال عضویت اجباری شروع ربات اضافه شد.\n\n"
        "از این به بعد کاربر بعد از /start اول باید عضو این کانال شود، بعد منوی اصلی را می‌بیند.\n\n"
        f"ID: <code>{item.id}</code>\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>",
        reply_markup=admin_menu(),
    )


async def _save_quick_section_channel(message: Message, section_key: str, channel_text: str) -> None:
    if section_key not in SECTION_TITLES:
        await message.answer(f"❌ بخش نامعتبر است. کلیدهای مجاز: <code>{SECTION_KEY_HELP}</code>")
        return

    raw = (channel_text or "").strip()
    if not raw:
        await message.answer("❌ اسم کانال خالی است. مثلا بنویس: <code>@YourChannel</code>")
        return

    parts = raw.split(maxsplit=1)
    chat_id = parts[0].strip()
    link = parts[1].strip() if len(parts) > 1 else None

    try:
        item = await _validate_and_save_section_channel(message.bot, section_key=section_key, chat_id=chat_id, link=link)
    except Exception as e:
        await message.answer(
            "❌ کانال اضافه نشد.\n\n"
            "ربات باید داخل آن کانال ادمین باشد و مقدار کانال درست باشد.\n"
            "برای کانال عمومی نمونه: <code>@YourChannel</code>\n"
            "برای کانال خصوصی نمونه: <code>-1001234567890 https://t.me/+InviteLink</code>\n\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return

    await message.answer(
        "✅ کانال اختصاصی اضافه شد.\n\n"
        f"بخش: <b>{SECTION_TITLES.get(item.section_key, item.section_key)}</b>\n"
        f"ID: <code>{item.id}</code>\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>"
    )


async def _quick_section_command(message: Message, state: FSMContext, section_key: str) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        await _save_quick_section_channel(message, section_key, parts[1])
        return

    await state.set_state(AddSectionChannelState.channel)
    await state.update_data(section_key=section_key)
    await message.answer(
        f"➕ افزودن کانال برای بخش <b>{SECTION_TITLES[section_key]}</b>\n\n"
        "فقط اسم کانال را بفرست. نمونه:\n"
        "<code>@YourChannel</code>\n\n"
        "اگر کانال خصوصی است، این مدل را بفرست:\n"
        "<code>-1001234567890 https://t.me/+InviteLink</code>"
    )


@router.message(Command("addvpnchannel"))
async def add_vpn_section_channel_handler(message: Message, state: FSMContext) -> None:
    await _quick_section_command(message, state, "vpn")


@router.message(Command("addaccountchannel"))
async def add_account_section_channel_handler(message: Message, state: FSMContext) -> None:
    await _quick_section_command(message, state, "accounts")


@router.message(Command("addtelegramchannel"))
async def add_telegram_section_channel_handler(message: Message, state: FSMContext) -> None:
    await _quick_section_command(message, state, "telegram")


@router.message(Command("addcontactchannel"))
async def add_contact_section_channel_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("گزینه ارتباط با تیم ما عضویت اجباری جداگانه ندارد؛ برای این بخش کانال اضافه نمی‌شود.")


async def _edit_main_required_channel(message: Message, channel_id: int, channel_text: str) -> None:
    raw = (channel_text or "").strip()
    if not raw:
        await message.answer("❌ اسم کانال خالی است. مثلا بنویس: <code>@YourChannel</code>")
        return
    parts = raw.split(maxsplit=1)
    chat_id = parts[0].strip()
    link = parts[1].strip() if len(parts) > 1 else None
    try:
        chat = await message.bot.get_chat(chat_id)
        title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
        if not link and getattr(chat, "username", None):
            link = f"https://t.me/{chat.username}"
        item = await crud.update_required_channel(channel_id, chat_id=str(chat_id), link=link, title=title)
    except Exception as e:
        await message.answer(
            "❌ کانال ادیت نشد.\n\n"
            "ربات باید داخل کانال ادمین باشد و مقدار کانال درست باشد.\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return
    if not item:
        await message.answer("❌ کانال پیدا نشد.")
        return
    await message.answer(
        "✅ کانال عضویت اجباری شروع ربات ادیت شد.\n\n"
        f"ID: <code>{item.id}</code>\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>",
        reply_markup=admin_menu(),
    )


async def _edit_section_required_channel(message: Message, section_key: str, channel_id: int, channel_text: str) -> None:
    if section_key not in SECTION_TITLES:
        await message.answer(f"❌ بخش نامعتبر است. کلیدهای مجاز: <code>{SECTION_KEY_HELP}</code>")
        return
    raw = (channel_text or "").strip()
    if not raw:
        await message.answer("❌ اسم کانال خالی است. مثلا بنویس: <code>@YourChannel</code>")
        return
    parts = raw.split(maxsplit=1)
    chat_id = parts[0].strip()
    link = parts[1].strip() if len(parts) > 1 else None
    try:
        chat = await message.bot.get_chat(chat_id)
        title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
        if not link and getattr(chat, "username", None):
            link = f"https://t.me/{chat.username}"
        item = await crud.update_section_required_channel(channel_id, chat_id=str(chat_id), link=link, title=title)
    except Exception as e:
        await message.answer(
            "❌ کانال ادیت نشد.\n\n"
            "ربات باید داخل کانال ادمین باشد و مقدار کانال درست باشد.\n"
            f"Error: <code>{type(e).__name__}: {e}</code>"
        )
        return
    if not item:
        await message.answer("❌ کانال پیدا نشد.")
        return
    await message.answer(
        "✅ کانال اختصاصی بخش ادیت شد.\n\n"
        f"بخش: <b>{SECTION_TITLES.get(section_key, section_key)}</b>\n"
        f"ID: <code>{item.id}</code>\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"Chat: <code>{item.chat_id}</code>\n"
        f"Link: <code>{item.link or '-'}</code>",
        reply_markup=admin_menu(),
    )


@router.message(AddSectionChannelState.channel)
async def add_section_channel_state_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    target_type = data.get("target_type", "section")
    section_key = data.get("section_key")
    await state.clear()

    if target_type == "main":
        await _save_main_required_channel(message, message.text or "")
        return

    if target_type == "edit_main":
        await _edit_main_required_channel(message, int(data.get("edit_id", 0)), message.text or "")
        return

    if target_type == "edit_section":
        await _edit_section_required_channel(message, str(section_key or ""), int(data.get("edit_id", 0)), message.text or "")
        return

    await _save_quick_section_channel(message, str(section_key or ""), message.text or "")


@router.message(Command("delsectionchannel"))
async def del_section_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("فرمت درست:\n<code>/delsectionchannel 1</code>")
        return

    channel_id = int(parts[1].strip())
    ok = await crud.disable_section_required_channel(channel_id)
    if ok:
        await message.answer(f"✅ کانال اختصاصی {channel_id} غیرفعال شد.")
    else:
        await message.answer("❌ کانال پیدا نشد.")


@router.message(Command("clearsection"))
async def clear_section_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip() not in SECTION_TITLES:
        await message.answer(f"فرمت درست:\n<code>/clearsection vpn</code>\n\nکلیدها: <code>{SECTION_KEY_HELP}</code>")
        return

    section_key = parts[1].strip()
    await crud.clear_section_required_channels(section_key)
    await message.answer(f"✅ همه کانال‌های بخش {SECTION_TITLES[section_key]} غیرفعال شد.")


@router.message(Command("debug_section"))
async def debug_section_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or parts[1].strip() not in SECTION_TITLES:
        await message.answer(f"فرمت درست:\n<code>/debug_section vpn</code>\n\nکلیدها: <code>{SECTION_KEY_HELP}</code>")
        return

    section_key = parts[1].strip()
    channels = await get_section_join_channels(section_key)
    if not channels:
        await message.answer(f"❌ برای بخش {SECTION_TITLES[section_key]} کانال فعالی ثبت نشده است.")
        return

    lines = [f"🧪 <b>تست کانال‌های بخش {SECTION_TITLES[section_key]}</b>"]
    for ch in channels:
        lines.append(
            "\n--------------------\n"
            f"Title: <b>{ch.get('title') or '-'}</b>\n"
            f"Chat: <code>{ch.get('chat_id')}</code>\n"
            f"Link: <code>{ch.get('link') or 'خالی'}</code>"
        )
        try:
            chat = await message.bot.get_chat(ch["chat_id"])
            lines.append("✅ ربات کانال را می‌بیند.")
            lines.append(f"Chat ID: <code>{chat.id}</code>")
            if getattr(chat, "username", None):
                lines.append(f"Username: @{chat.username}")
        except Exception as e:
            lines.append("❌ ربات نمی‌تواند کانال را ببیند.")
            lines.append("راه‌حل: ربات را داخل کانال ادمین کن.")
            lines.append(f"Error: <code>{type(e).__name__}: {e}</code>")

    await message.answer("\n".join(lines))


@router.message(Command("debug_channel"))
async def debug_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    lines = ["🧪 <b>تست کانال‌های عضویت</b>"]

    channels = await get_join_channels()
    if not channels:
        await message.answer("❌ هیچ کانال اجباری فعالی تنظیم نشده است.")
        return

    for ch in channels:
        lines.append(
            "\n--------------------\n"
            f"Title: <b>{ch.get('title') or '-'}</b>\n"
            f"Chat: <code>{ch.get('chat_id')}</code>\n"
            f"Link: <code>{ch.get('link') or 'خالی'}</code>"
        )
        try:
            chat = await message.bot.get_chat(ch["chat_id"])
            lines.append("✅ ربات کانال را می‌بیند.")
            lines.append(f"Chat ID: <code>{chat.id}</code>")
            if getattr(chat, "username", None):
                lines.append(f"Username: @{chat.username}")
        except Exception as e:
            lines.append("❌ ربات نمی‌تواند کانال را ببیند.")
            lines.append("راه‌حل: ربات را داخل کانال ادمین کن.")
            lines.append(f"Error: <code>{type(e).__name__}: {e}</code>")

    await message.answer("\n".join(lines))




def get_sqlite_db_path() -> str:
    """Extract SQLite database file path from DATABASE_URL."""
    raw = str(DATABASE_URL or "").strip()
    if raw.startswith("sqlite+aiosqlite:////"):
        return "/" + raw.split("sqlite+aiosqlite:////", 1)[1]
    if raw.startswith("sqlite+aiosqlite:///"):
        return raw.split("sqlite+aiosqlite:///", 1)[1]
    if raw.startswith("sqlite:///"):
        return raw.split("sqlite:///", 1)[1]
    return "/app/data/bot.db"


async def send_database_backup(bot: Bot, reason: str = "manual") -> None:
    db_path = get_sqlite_db_path()
    path = Path(db_path)

    if not path.exists():
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"❌ فایل دیتابیس برای بکاپ پیدا نشد.\n\nPath: <code>{db_path}</code>"
                )
            except Exception:
                pass
        return

    caption = (
        "💾 <b>بکاپ دیتابیس movie-bot</b>\n\n"
        f"نسخه: <code>{BOT_VERSION}</code>\n"
        f"نوع بکاپ: <code>{reason}</code>\n\n"
        "این فایل را داخل GitHub عمومی آپلود نکن."
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                chat_id=admin_id,
                document=FSInputFile(str(path), filename="bot_backup.db"),
                caption=caption,
            )
        except Exception as e:
            logging.warning("auto/manual backup failed for admin %s: %s", admin_id, e)


async def auto_backup_loop(bot: Bot) -> None:
    if not AUTO_BACKUP_ENABLED:
        logging.info("Auto backup is disabled.")
        return

    hours = max(1, int(AUTO_BACKUP_HOURS or 24))
    seconds = hours * 60 * 60

    if AUTO_BACKUP_ON_START:
        await asyncio.sleep(20)
        await send_database_backup(bot, reason="startup")

    logging.info("Auto backup enabled: every %s hours", hours)

    while True:
        await asyncio.sleep(seconds)
        await send_database_backup(bot, reason=f"auto-every-{hours}h")



# ============================================================
# ارسال همگانی به کاربران ربات
# ============================================================

def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ ارسال به همه کاربران فعال", callback_data="broadcast:send")],
            [InlineKeyboardButton(text="❌ لغو ارسال همگانی", callback_data="broadcast:cancel")],
        ]
    )


@router.message(F.text == BTN_BROADCAST)
@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await state.set_state(BroadcastState.content)

    users_count = await crud.count_users()

    await message.answer(
        "📣 <b>ارسال همگانی</b>\n\n"
        f"کاربران ثبت‌شده در دیتابیس: <code>{users_count}</code>\n\n"
        "متن، عکس، ویدیو، گیف، فایل یا همان پست کانالی که می‌خواهی برای کاربران بفرستی را همینجا ارسال کن.\n\n"
        "می‌تونی از کانال هم Forward کنی.\n\n"
        "بعد از ارسال محتوا، ربات قبل از ارسال همگانی ازت تایید می‌گیرد.\n\n"
        "برای لغو: /cancel"
    )


@router.message(BroadcastState.content)
async def broadcast_receive_content(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    # پیام دستوری را به عنوان محتوا قبول نکنیم، مگر خود ادمین بخواهد متن معمولی بفرستد.
    if (message.text or "").strip() in {"/cancel", BTN_HELP, BTN_BROADCAST}:
        await state.clear()
        await message.answer("❌ ارسال همگانی لغو شد.", reply_markup=admin_menu())
        return

    reply_markup_data = None
    if message.reply_markup:
        try:
            reply_markup_data = message.reply_markup.model_dump(mode="json")
        except Exception:
            reply_markup_data = None

    await state.update_data(
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        reply_markup_data=reply_markup_data,
    )
    await state.set_state(BroadcastState.confirm)

    users_count = await crud.count_users()
    buttons_status = "✅ دکمه شیشه‌ای تشخیص داده شد و همراه پیام ارسال می‌شود." if reply_markup_data else "⚠️ دکمه شیشه‌ای داخل این پیام تشخیص داده نشد."

    await message.answer(
        "✅ محتوا دریافت شد.\n\n"
        f"تعداد کاربران ثبت‌شده: <code>{users_count}</code>\n\n"
        f"{buttons_status}\n\n"
        "برای شروع ارسال همگانی، تایید کن.\n\n"
        "نکته: اگر بعضی کاربران ربات را بلاک کرده باشند، ارسال برای آن‌ها ناموفق ثبت می‌شود.",
        reply_markup=broadcast_confirm_kb(),
    )


@router.callback_query(BroadcastState.confirm, F.data == "broadcast:cancel")
async def broadcast_cancel_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    await state.clear()
    await call.message.answer("❌ ارسال همگانی لغو شد.", reply_markup=admin_menu())
    await call.answer()


@router.callback_query(BroadcastState.confirm, F.data == "broadcast:send")
async def broadcast_send_callback(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی نداری.", show_alert=True)
        return

    data = await state.get_data()
    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")

    if not from_chat_id or not message_id:
        await state.clear()
        await call.message.answer("❌ محتوای ارسال همگانی پیدا نشد. دوباره شروع کن.", reply_markup=admin_menu())
        await call.answer()
        return

    users = await crud.get_users()
    targets = [u.telegram_id for u in users if u.telegram_id not in ADMIN_IDS]

    await call.message.answer(
        "⏳ ارسال همگانی شروع شد...\n\n"
        f"تعداد کاربران هدف: <code>{len(targets)}</code>\n"
        "تا پایان ارسال صبر کن."
    )
    await call.answer()

    reply_markup = None
    reply_markup_data = data.get("reply_markup_data")
    if reply_markup_data:
        try:
            reply_markup = InlineKeyboardMarkup.model_validate(reply_markup_data)
        except Exception:
            reply_markup = None

    sent = 0
    failed = 0
    blocked = 0

    for user_id in targets:
        try:
            await call.bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
            )
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            failed += 1
        except Exception:
            failed += 1

        # رعایت محدودیت ارسال تلگرام و جلوگیری از فشار زیاد
        await asyncio.sleep(0.05)

    await state.clear()

    await call.message.answer(
        "✅ ارسال همگانی تمام شد.\n\n"
        f"موفق: <code>{sent}</code>\n"
        f"ناموفق: <code>{failed}</code>\n"
        f"بلاک کرده‌اند/دسترسی نیست: <code>{blocked}</code>",
        reply_markup=admin_menu(),
    )


@router.message(F.text == BTN_BACKUP)
@router.message(Command("backup"))
async def backup_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("⏳ در حال آماده‌سازی بکاپ دیتابیس...")
    await send_database_backup(message.bot, reason="manual")



@router.message()
async def unknown_handler(message: Message) -> None:
    if is_admin(message.from_user.id):
        await message.answer("از منوی ادمین استفاده کن یا /help را بزن.", reply_markup=admin_menu())
    else:
        await message.answer("از منوی پایین یکی از گزینه‌ها را انتخاب کن 👇", reply_markup=user_menu())


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    logging.basicConfig(level=logging.INFO)
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # پاک‌سازی دستورهای قدیمی تلگرام در منوی شناور "/"
    # این کار باعث می‌شود دستورهای روش قبلی مثل addvpnchannel و addsectionchannel باقی نمانند.
    try:
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
    except Exception:
        pass

    for admin_id in ADMIN_IDS:
        try:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            pass

    # کاربران عادی فقط دستورهای ساده را می‌بینند.
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="شروع ربات"),
            BotCommand(command="help", description="راهنما"),
        ],
        scope=BotCommandScopeDefault(),
    )

    # ادمین‌ها فقط دستورهای ضروری فعلی را در منوی شناور "/" می‌بینند.
    admin_commands = [
        BotCommand(command="start", description="شروع ربات / پنل ادمین"),
        BotCommand(command="help", description="راهنمای ادمین"),
        BotCommand(command="add", description="ثبت فایل جدید"),
        BotCommand(command="files", description="لیست فایل‌ها"),
        BotCommand(command="stats", description="آمار ربات"),        BotCommand(command="channels", description="مدیریت کانال‌های اجباری"),
        BotCommand(command="addchannel", description="باز کردن منوی مدیریت کانال اجباری"),
        BotCommand(command="cancel", description="لغو عملیات فعلی"),
        BotCommand(command="version", description="نمایش نسخه فعال"),
        BotCommand(command="backup", description="دریافت بکاپ دیتابیس"),
        BotCommand(command="post", description="ساخت پست دکمه‌دار کانال"),
        BotCommand(command="posts", description="لیست پست‌های منتشرشده"),
        BotCommand(command="broadcast", description="ارسال همگانی"),
    ]

    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            pass

    print("Bot started — movie-bot-v9.3-broadcast-buttons-fix")
    asyncio.create_task(auto_backup_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
