# Movie Locker Bot — Latest Files

آخرین نسخه تمیز پروژه Movie Locker Bot.

## قابلیت‌ها

- ثبت فایل توسط ادمین
- دریافت فایل با لینک `?start=f_ID`
- عضویت اجباری در کانال اصلی
- ارسال فایل بعد از تایید عضویت
- حذف خودکار فایل بعد از زمان مشخص
- حذف پیام هشدار بعد از حذف فایل
- بدون ارسال پیام «زمان مشاهده فایل تمام شد»

## فایل‌ها

- `main.py`
- `config.py`
- `database.py`
- `crud.py`
- `requirements.txt`
- `railway.json`
- `.python-version`
- `.gitignore`
- `.env.example`
- `README.md`

## اجرای لوکال

```cmd
.venv\Scripts\activate.bat
python -m py_compile main.py
python main.py
```

## Railway Variables

```env
BOT_TOKEN=توکن ربات
ADMIN_IDS=آیدی عددی ادمین
DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db
REQUIRED_CHANNEL=@irfreenet
REQUIRED_CHANNEL_LINK=https://t.me/irfreenet
DELETE_AFTER_SECONDS=15
SKIP_MEMBERSHIP_FOR_ADMINS=1
```

## آپلود نکن

```text
.env
bot.db
.venv
__pycache__
```
