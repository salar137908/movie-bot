# Movie Locker Bot — Bot Only Channel Management

در این نسخه دیگر لازم نیست کانال‌های اجباری را داخل Railway Variables وارد کنی.
ادمین همه کانال‌های اجباری را از داخل خود ربات مدیریت می‌کند.

## Railway Variables لازم

فقط این‌ها لازم است:

```env
BOT_TOKEN=توکن ربات
ADMIN_IDS=آیدی عددی ادمین
DATABASE_URL=sqlite+aiosqlite:////app/data/bot.db
DELETE_AFTER_SECONDS=15
SKIP_MEMBERSHIP_FOR_ADMINS=1
```

دیگر لازم نیست این‌ها را در Railway بزنی:

```env
REQUIRED_CHANNEL
REQUIRED_CHANNEL_LINK
```

## مدیریت کانال‌ها داخل ربات

نمایش پنل کانال‌ها:

```text
/channels
```

افزودن کانال عمومی:

```text
/addchannel @irfreenet
```

جایگزینی همه کانال‌های قبلی با یک کانال:

```text
/setchannel @irfreenet
```

حذف کانال:

```text
/delchannel1
```

برای کانال خصوصی:

```text
/addchannel -1001234567890 https://t.me/+InviteLink
```

## دکمه شیشه‌ای عضویت

برای کانال عمومی، وقتی با `/addchannel @username` اضافه شود، ربات خودش لینک شیشه‌ای را می‌سازد:

```text
https://t.me/username
```

برای کانال خصوصی، چون یوزرنیم عمومی ندارد، باید لینک دعوت را بدهی.

## نکته مهم

ربات باید داخل هر کانال اجباری Admin باشد تا بتواند عضویت کاربران را بررسی کند.

## آپلود نکن

```text
.env
bot.db
.venv
__pycache__
```


## منوی شناور / برای ادمین

در این نسخه وقتی ادمین داخل ربات `/` بزند، دستورهای مدیریتی را به صورت شناور می‌بیند:

```text
/add
/files
/stats
/channels
/addchannel
/setchannel
/delchannel
/debug_channel
```

نکته: خود تلگرام فقط نام دستور را در منوی شناور نشان می‌دهد، نه آرگومان کامل.  
برای مثال بعد از انتخاب `/addchannel` باید ادامه‌اش را خودت بنویسی:

```text
/addchannel @irfreenet
```

یا برای کانال خصوصی:

```text
/addchannel -1001234567890 https://t.me/+InviteLink
```
