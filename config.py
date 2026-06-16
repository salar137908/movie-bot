import os
from dotenv import load_dotenv

load_dotenv()


def _csv_int(value: str) -> list[int]:
    result: list[int] = []
    for item in str(value or "").replace(" ", "").split(","):
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            pass
    return result


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = _csv_int(os.getenv("ADMIN_IDS", ""))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db").strip()

# کانال اصلی اجباری؛ می‌تواند @username یا -100xxxxxxxxxx باشد
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "").strip()
REQUIRED_CHANNEL_LINK = os.getenv("REQUIRED_CHANNEL_LINK", "").strip()

# کانال خصوصی آرشیو؛ برای کپی فایل از آرشیو بهتر است -100xxxxxxxxxx باشد
ARCHIVE_CHANNEL_ID = os.getenv("ARCHIVE_CHANNEL_ID", "").strip()

# زمان حذف فایل ارسال‌شده برای کاربر
DELETE_AFTER_SECONDS = int(os.getenv("DELETE_AFTER_SECONDS", "15"))

# اگر 1 باشد ادمین‌ها بدون عضویت هم فایل می‌گیرند
SKIP_MEMBERSHIP_FOR_ADMINS = os.getenv("SKIP_MEMBERSHIP_FOR_ADMINS", "1").lower() in {"1", "true", "yes", "on"}


AUTO_BACKUP_ENABLED: bool = os.getenv("AUTO_BACKUP_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
AUTO_BACKUP_HOURS: int = int(os.getenv("AUTO_BACKUP_HOURS", "24"))
AUTO_BACKUP_ON_START: bool = os.getenv("AUTO_BACKUP_ON_START", "0").strip().lower() in {"1", "true", "yes", "on"}
