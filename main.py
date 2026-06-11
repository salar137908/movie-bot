import asyncio
import logging
import re
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
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
    DELETE_AFTER_SECONDS,
    REQUIRED_CHANNEL,
    REQUIRED_CHANNEL_LINK,
    SKIP_MEMBERSHIP_FOR_ADMINS,
)
from database import init_db

# ============================================================
# مرکز کنترل متن‌ها و دکمه‌ها
# ============================================================
BOT_TITLE = "🎬 ربات دریافت فایل"
WELCOME_TEXT = "سلام 👋\nبرای دریافت فایل، از لینک مخصوص داخل کانال وارد ربات شوید."
ADMIN_WELCOME_TEXT = "سلام ادمین 👋\nاز منوی زیر فایل‌ها را مدیریت کن."

BTN_ADD_FILE = "➕ ثبت فایل"
BTN_FILES = "📋 لیست فایل‌ها"
BTN_STATS = "📊 آمار"
BTN_HELP = "📌 راهنما"
BTN_CHANNELS = "📢 کانال‌های اجباری"

JOIN_REQUIRED_TEXT = "🔒 برای دریافت فایل، ابتدا عضو کانال شوید.\n\nبعد از عضویت، به همین ربات برگردید و روی «✅ بررسی عضویت» بزنید 👇"
BTN_JOIN_CHANNEL = "📢 عضویت در کانال"
BTN_CHECK_JOIN = "✅ بررسی عضویت"

FILE_NOT_FOUND_TEXT = "❌ این فایل پیدا نشد یا غیرفعال شده است."
FILE_SENDING_TEXT = "⏳ فایل در حال ارسال است..."
FILE_WARNING_TEXT = "⚠️ این فایل بعد از ۱۵ ثانیه حذف می‌شود.\n\nاگر نیاز دارید، همین حالا آن را در Saved Messages تلگرام ذخیره کنید."

# اگر نمی‌خواهی پیام دیباگ حذف برای ادمین بیاید، False بماند.
DELETE_DEBUG_TO_ADMIN = False


ADMIN_HELP_TEXT = """
📌 <b>راهنمای ادمین</b>

➕ ثبت فایل:
اول فایل را داخل کانال خصوصی آرشیو آپلود کن.
بعد داخل ربات دکمه «ثبت فایل» را بزن و همان پیام فایل را از کانال آرشیو برای ربات فوروارد کن.

دستورها:
/files — لیست فایل‌ها
/del<ID> — غیرفعال کردن فایل، مثال: /del12
/stats — آمار
/debug_channel — تست تنظیمات کانال عضویت
/channels — مدیریت کانال‌های اجباری
/addchannel @username — افزودن کانال اجباری
/setchannel @username — جایگزینی کانال اجباری
/delchannel<ID> — حذف کانال اجباری، مثال: /delchannel3
""".strip()

# ============================================================

router = Router()


class AddFileState(StatesGroup):
    title = State()
    forwarded_file = State()


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD_FILE), KeyboardButton(text=BTN_FILES)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_CHANNELS)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


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

    if not await is_member(message.bot, message.from_user.id):
        if not REQUIRED_CHANNEL_LINK:
            await message.answer(
                "⚠️ لینک عضویت کانال تنظیم نشده است. لطفاً به ادمین اطلاع بده."
            )
            await notify_admins(
                message.bot,
                "⚠️ REQUIRED_CHANNEL_LINK تنظیم نشده است.\n"
                "برای نمایش دکمه عضویت، داخل .env این مقدار را بگذار:\n"
                "<code>REQUIRED_CHANNEL_LINK=https://t.me/YourChannel</code>"
            )
            return

        await message.answer(JOIN_REQUIRED_TEXT, reply_markup=await join_keyboard(payload))
        return

    await send_file_to_user(message.bot, message.chat.id, file_id)


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

    if is_admin(message.from_user.id):
        await message.answer(ADMIN_WELCOME_TEXT, reply_markup=admin_menu())
    else:
        await message.answer(WELCOME_TEXT)


@router.callback_query(F.data.startswith("check:"))
async def check_join_callback(call: CallbackQuery) -> None:
    payload = call.data.split(":", 1)[1]
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
        await message.answer(WELCOME_TEXT)
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


@router.message(F.text == BTN_FILES)
@router.message(Command("files"))
async def files_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    items = await crud.get_files(limit=20)
    if not items:
        await message.answer("هنوز فایلی ثبت نشده است.")
        return

    me = await message.bot.get_me()
    lines = ["📋 <b>لیست فایل‌ها</b>\n"]
    for item in items:
        status = "✅ فعال" if item.is_active else "❌ غیرفعال"
        link = f"https://t.me/{me.username}?start=f_{item.id}"
        lines.append(
            f"{status}\n"
            f"ID: <code>{item.id}</code>\n"
            f"عنوان: {item.title}\n"
            f"نوع: <code>{getattr(item, 'file_type', None) or 'old'}</code>\n"
            f"بازدید: {item.views}\n"
            f"لینک: <code>{link}</code>\n"
            f"حذف: /del{item.id}\n"
        )
    await message.answer("\n".join(lines))


@router.message(F.text.regexp(r"^/del\d+$"))
async def delete_file_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    file_id = int(message.text.replace("/del", ""))
    ok = await crud.disable_file(file_id)
    if ok:
        await message.answer(f"✅ فایل {file_id} غیرفعال شد.")
    else:
        await message.answer("❌ فایل پیدا نشد.")


@router.message(F.text == BTN_CHANNELS)
@router.message(Command("channels"))
async def channels_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    db_channels = await crud.get_required_channels(active_only=False)
    lines = ["📢 <b>مدیریت کانال‌های اجباری</b>\n"]

    if db_channels:
        for ch in db_channels:
            status = "✅ فعال" if ch.is_active else "❌ غیرفعال"
            lines.append(
                f"{status}\n"
                f"ID: <code>{ch.id}</code>\n"
                f"عنوان: <b>{ch.title or '-'}</b>\n"
                f"Chat: <code>{ch.chat_id}</code>\n"
                f"Link: <code>{ch.link or '-'}</code>\n"
                f"حذف: /delchannel{ch.id}\n"
            )
    else:
        lines.append("هنوز کانالی از داخل ربات ثبت نشده است.")
        if REQUIRED_CHANNEL:
            lines.append(
                "\nفعلاً ربات از تنظیمات Railway/.env استفاده می‌کند:\n"
                f"REQUIRED_CHANNEL: <code>{REQUIRED_CHANNEL}</code>\n"
                f"REQUIRED_CHANNEL_LINK: <code>{REQUIRED_CHANNEL_LINK or 'خالی'}</code>"
            )

    lines.append(
        "\n<b>دستورها:</b>\n"
        "افزودن کانال عمومی:\n"
        "<code>/addchannel @irfreenet</code>\n\n"
        "جایگزینی همه کانال‌ها با یک کانال:\n"
        "<code>/setchannel @irfreenet</code>\n\n"
        "اگر کانال خصوصی است:\n"
        "<code>/addchannel -1001234567890 https://t.me/+InviteLink</code>\n\n"
        "حذف کانال:\n"
        "<code>/delchannelID</code>"
    )
    await message.answer("\n".join(lines))


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
            "فرمت درست:\n"
            "<code>/addchannel @irfreenet</code>\n\n"
            "برای کانال خصوصی:\n"
            "<code>/addchannel -1001234567890 https://t.me/+InviteLink</code>"
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
async def delete_channel_handler(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return

    channel_id = int(message.text.replace("/delchannel", ""))
    ok = await crud.disable_required_channel(channel_id)
    if ok:
        await message.answer(f"✅ کانال اجباری {channel_id} غیرفعال شد.")
    else:
        await message.answer("❌ کانال پیدا نشد.")


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
        await message.answer(WELCOME_TEXT)


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

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="شروع ربات"),
            BotCommand(command="help", description="راهنما"),
            BotCommand(command="channels", description="مدیریت کانال‌های اجباری"),
        ]
    )

    print("Bot started — dynamic-required-channels")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
