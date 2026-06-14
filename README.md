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


## نسخه movie-section-gate-v1

در این نسخه برای کاربران چهار دکمه اصلی اضافه شده است:

- 📢 کانال تلگرام
- 🔐 فیلترشکن پرمیوم رایگان
- 💎 دریافت اکانت های پولی سایت های معروف
- ☎️ ارتباط با تیم ما

هر دکمه کانال‌های عضویت اجباری جداگانه خودش را دارد.

کلیدهای هر بخش:

- `telegram` برای کانال تلگرام
- `vpn` برای فیلترشکن پرمیوم رایگان
- `accounts` برای بخش اکانت‌ها
- `contact` برای ارتباط با تیم ما

نمونه افزودن کانال برای فیلترشکن:

```text
/addsectionchannel vpn @channel1
/addsectionchannel vpn @channel2
/addsectionchannel vpn @channel3
/addsectionchannel vpn @channel4
```

نمونه افزودن کانال برای اکانت‌ها:

```text
/addsectionchannel accounts @channelA
/addsectionchannel accounts @channelB
```

برای دیدن لیست کانال‌های اختصاصی:

```text
/sectionchannels
```

برای حذف کانال اختصاصی:

```text
/delsectionchannel 1
```

نکته: برای بخش اکانت‌ها فقط اطلاعات یا لینک‌هایی را قرار بده که مجوز انتشارش را داری.


## نسخه v2 — دستورهای سریع ادمین برای افزودن کانال

تلگرام اجازه نمی‌دهد متن کامل همراه آرگومان به صورت خودکار داخل باکس تایپ نوشته شود. برای همین در این نسخه دستورهای کوتاه جدا اضافه شده‌اند. ادمین وقتی `/` را بزند این دستورها را می‌بیند:

- `/addvpnchannel`
- `/addaccountchannel`
- `/addtelegramchannel`
- `/addcontactchannel`

روش استفاده سریع:

```text
/addvpnchannel @channel1
/addaccountchannel @channel2
/addtelegramchannel @channel3
/addcontactchannel @channel4
```

اگر ادمین فقط خود دستور را بفرستد، ربات مرحله بعدی را باز می‌کند و فقط اسم کانال را می‌پرسد. برای کانال خصوصی هم این قالب را بفرست:

```text
-1001234567890 https://t.me/+InviteLink
```

بعد از Deploy داخل Railway Logs باید این عبارت دیده شود:

```text
Bot started — movie-section-gate-v2-quick-admin-commands
```
