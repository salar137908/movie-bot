import asyncio
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
BOT_VERSION = "movie-bot-v7.7-direct-buttons-backup"
BOT_TITLE = "🎬 ربات دریافت فایل"
WELCOME_TEXT = "سلام 👋\nبرای دریافت فایل، از لینک مخصوص داخل کانال وارد ربات شوید."
ADMIN_WELCOME_TEXT = "سلام ادمین 👋\nاز منوی زیر فایل‌ها را مدیریت کن."

BTN_ADD_FILE = "➕ ثبت فایل"
BTN_FILES = "📋 لیست فایل‌ها"
BTN_STATS = "📊 آمار"
BTN_BACKUP = "💾 بکاپ دیتابیس"
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

JOIN_REQUIRED_TEXT = "🔒 برای استفاده از ربات، ابتدا عضو کانال‌های زیر شوید.\n\nبعد از عضویت، به همین ربات برگردید و روی «✅ بررسی عضویت» بزنید 👇"
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
        "• عضویت اجباری شروع ربات: برای /start و لینک فایل\n"
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


async def join_keyboard(payload: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    channels = await get_join_channels()

    for ch in channels:
        if ch.get("link"):
            title = ch.get("title") or "کانال"
            rows.append([InlineKeyboardButton(text=f"{BTN_JOIN_CHANNEL} {title}", url=ch["link"])])

    rows.append([InlineKeyboardButton(text=BTN_CHECK_JOIN, callback_data=f"check:{payload}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



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


async def section_join_keyboard(section_key: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    channels = await get_section_join_channels(section_key)

    for ch in channels:
        if ch.get("link"):
            title = ch.get("title") or "کانال"
            rows.append([InlineKeyboardButton(text=f"{BTN_JOIN_CHANNEL} {title}", url=ch["link"])])

    rows.append([InlineKeyboardButton(text=BTN_CHECK_JOIN, callback_data=f"section_check:{section_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def is_section_member(bot: Bot, user_id: int, section_key: str) -> bool:
    if is_admin(user_id) and SKIP_MEMBERSHIP_FOR_ADMINS:
        return True

    channels = await get_section_join_channels(section_key)
    if not channels:
        return False

    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status not in {"creator", "administrator", "member"}:
                return False
        except Exception:
            return False

    return True


def section_join_text(section_key: str) -> str:
    title = SECTION_TITLES.get(section_key, "این بخش")
    return (
        f"🔒 برای استفاده از بخش «{title}» باید عضو کانال‌های همین بخش شوی.\n\n"
        "بعد از عضویت، به ربات برگرد و روی «✅ بررسی عضویت» بزن 👇"
    )


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
        await message.answer(section_join_text(section_key), reply_markup=await section_join_keyboard(section_key))
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
    if is_admin(user_id) and SKIP_MEMBERSHIP_FOR_ADMINS:
        return True

    channels = await get_join_channels()
    if not channels:
        return True

    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chat_id"], user_id)
            if member.status not in {"creator", "administrator", "member"}:
                return False
        except Exception:
            return False

    return True


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
    file_id = extract_file_id_from_payload(payload)
    if file_id is None:
        await message.answer(WELCOME_TEXT)
        return

    # نسخه v6:
    # لینک فایل هم از همان عضویت اجباری عمومی داخل دیتابیس استفاده می‌کند.
    # دیگر به REQUIRED_CHANNEL_LINK داخل Railway وابسته نیست.
    if not await is_member(message.bot, message.from_user.id):
        await message.answer(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard(payload))
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
        await message.answer(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard("menu"))
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
        await call.message.answer(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard("menu"))
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
        await message.answer(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard("menu"))
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
            await call.message.edit_text(section_join_text(section_key), reply_markup=await section_join_keyboard(section_key))
        except Exception:
            pass
        return

    await call.answer("عضویت تایید شد ✅")
    try:
        await call.message.edit_text(SECTION_RESULT_TEXTS.get(section_key, "✅ عضویت تایید شد."))
    except Exception:
        await call.message.answer(SECTION_RESULT_TEXTS.get(section_key, "✅ عضویت تایید شد."))


@router.callback_query(F.data.startswith("check:"))
async def check_join_callback(call: CallbackQuery) -> None:
    payload = call.data.split(":", 1)[1]

    # بررسی عضویت عمومی برای نمایش منوی اصلی ربات
    if payload == "menu":
        if not await is_member(call.bot, call.from_user.id):
            await call.answer("هنوز عضویت شما تایید نشده است.", show_alert=True)
            try:
                await call.message.edit_text(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard("menu"))
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
            await call.message.edit_text(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard(payload))
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
    await message.answer(f"📊 آمار ربات\n\n👥 کاربران: {users}\n🎬 فایل‌ها: {files}")




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
    await state.clear()

    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start=f_{item.id}"
    await message.answer(
        "✅ فایل ثبت شد.\n\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"نوع فایل: <code>{item.file_type}</code>\n"
        f"ID: <code>{item.id}</code>\n\n"
        f"لینک مخصوص:\n<code>{link}</code>\n\n"
        "این لینک را روی دکمه پست کانال اصلی بگذار."
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
                InlineKeyboardButton(text="🗑 حذف کامل", callback_data=f"filedelete:{file_id}"),
            ],
        ]
    )


async def send_file_card(message: Message, item, bot: Bot | None = None) -> None:
    bot = bot or message.bot
    me = await bot.get_me()
    status = "✅ فعال" if item.is_active else "❌ غیرفعال"
    link = f"https://t.me/{me.username}?start=f_{item.id}"
    text = (
        f"🎬 <b>فایل #{item.id}</b>\n\n"
        f"وضعیت: {status}\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"نوع: <code>{getattr(item, 'file_type', None) or 'old'}</code>\n"
        f"بازدید: <code>{item.views}</code>\n\n"
        f"لینک مخصوص:\n<code>{link}</code>"
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
    link = f"https://t.me/{me.username}?start=f_{item.id}"
    text = (
        f"🎬 <b>فایل #{item.id}</b>\n\n"
        f"وضعیت: {status}\n"
        f"عنوان: <b>{item.title}</b>\n"
        f"نوع: <code>{getattr(item, 'file_type', None) or 'old'}</code>\n"
        f"بازدید: <code>{item.views}</code>\n\n"
        f"لینک مخصوص:\n<code>{link}</code>"
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


@router.message()
async def unknown_handler(message: Message) -> None:
    if is_admin(message.from_user.id):
        await message.answer("از منوی ادمین استفاده کن یا /help را بزن.", reply_markup=admin_menu())
    else:
        await message.answer("از منوی پایین یکی از گزینه‌ها را انتخاب کن 👇", reply_markup=user_menu())




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


@router.message(F.text == BTN_BACKUP)
@router.message(Command("backup"))
async def backup_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("⏳ در حال آماده‌سازی بکاپ دیتابیس...")
    await send_database_backup(message.bot, reason="manual")


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
    ]

    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            pass

    print("Bot started — movie-bot-v7.7-direct-buttons-backup")
    asyncio.create_task(auto_backup_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
