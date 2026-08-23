import os
import time
import requests
import telebot
from telebot import types

# =========================
# تنظیمات
# =========================

# در Render این مقادیر را در Environment Variables قرار بده.
TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

ADMIN_ID = 6914909647

# قیمت را اینجا تغییر بده.
# Telegram برای خدمات دیجیتال از Telegram Stars (XTR) استفاده می‌کند.
# 250 Stars را به‌عنوان قیمت تقریبی پلن 5 دلاری تنظیم کرده‌ایم.
STAR_PRICE = 250

# مدت اشتراک: 30 روز
SUBSCRIPTION_SECONDS = 30 * 24 * 60 * 60

bot = telebot.TeleBot(TOKEN)

# فقط به‌عنوان fallback موقت؛ روی Render بعد از restart پاک می‌شود.
user_languages = {}
local_users = {}

# =========================
# مدیریت مالک و ادمین‌ها
# =========================
# مالک همیشه دسترسی کامل دارد.
# ادمین‌های دیگر از جدول فعلی admins در Supabase خوانده می‌شوند.
admin_cache = set()
admin_cache_time = 0
ADMIN_CACHE_SECONDS = 60


def _extract_admin_id(row):
    """ID ادمین را از چند نام رایج ستون در جدول admins پیدا می‌کند."""
    if not isinstance(row, dict):
        return None

    for key in ("user_id", "telegram_id", "admin_id", "id"):
        value = row.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None


def get_admin_ids(force=False):
    """ادمین‌ها را از جدول admins می‌خواند؛ در صورت خطا مالک همچنان فعال است."""
    global admin_cache, admin_cache_time

    if not force and time.time() - admin_cache_time < ADMIN_CACHE_SECONDS:
        return set(admin_cache)

    ids = {ADMIN_ID}

    if supabase_enabled():
        try:
            url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/admins"
            response = requests.get(
                url,
                headers=supabase_headers(),
                params={"select": "*"},
                timeout=10,
            )
            if response.ok:
                for row in response.json() or []:
                    value = _extract_admin_id(row)
                    if value is not None:
                        ids.add(value)
            else:
                print("Supabase admins read error:", response.status_code, response.text)
        except Exception as e:
            print("Admins read error:", e)

    admin_cache = ids
    admin_cache_time = time.time()
    return set(ids)


def is_admin(user_id):
    try:
        return int(user_id) in get_admin_ids()
    except (TypeError, ValueError):
        return False


def _admin_insert(user_id):
    """ادمین را به جدول موجود admins اضافه می‌کند.
    چون ساختار جدول قبلی را تغییر نمی‌دهیم، چند نام رایج ستون را امتحان می‌کند.
    """
    if not supabase_enabled():
        return False

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/admins"
    candidates = [
        {"user_id": int(user_id)},
        {"telegram_id": int(user_id)},
        {"admin_id": int(user_id)},
    ]

    for data in candidates:
        try:
            response = requests.post(
                url,
                headers=supabase_headers(),
                json=data,
                timeout=10,
            )
            if response.ok:
                get_admin_ids(force=True)
                return True
        except Exception as e:
            print("Admin insert error:", e)

    return False


def _admin_delete(user_id):
    """ادمین را از جدول admins حذف می‌کند؛ مالک هیچ‌وقت حذف نمی‌شود."""
    if int(user_id) == ADMIN_ID or not supabase_enabled():
        return False

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/admins"
    for column in ("user_id", "telegram_id", "admin_id", "id"):
        try:
            response = requests.delete(
                url,
                headers=supabase_headers(),
                params={column: f"eq.{int(user_id)}"},
                timeout=10,
            )
            if response.ok:
                get_admin_ids(force=True)
                return True
        except Exception as e:
            print("Admin delete error:", e)

    return False


def table_count(table):
    """تعداد ردیف‌های یک جدول را بدون وابستگی به ستون‌های آن می‌گیرد."""
    if not supabase_enabled():
        return 0

    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        headers = {
            **supabase_headers(),
            "Prefer": "count=exact",
        }
        response = requests.get(
            url,
            headers=headers,
            params={"select": "*", "limit": "1"},
            timeout=10,
        )
        if not response.ok:
            return 0

        content_range = response.headers.get("Content-Range", "")
        if "/" in content_range:
            total = content_range.split("/")[-1]
            if total.isdigit():
                return int(total)

        data = response.json()
        return len(data) if isinstance(data, list) else 0
    except Exception as e:
        print(f"{table} count error:", e)
        return 0


def get_bot_user_ids(limit=5000):
    if not supabase_enabled():
        return list(local_users.keys())[:limit]

    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/bot_users"
        response = requests.get(
            url,
            headers=supabase_headers(),
            params={"select": "user_id", "limit": str(limit)},
            timeout=10,
        )
        if response.ok:
            result = []
            for row in response.json() or []:
                try:
                    result.append(int(row["user_id"]))
                except (KeyError, TypeError, ValueError):
                    pass
            return result
    except Exception as e:
        print("User list error:", e)

    return list(local_users.keys())[:limit]


def admin_keyboard(language, owner=False):
    keyboard = types.InlineKeyboardMarkup()
    if language == "fa":
        keyboard.row(
            types.InlineKeyboardButton("📊 آمار", callback_data="admin_stats"),
            types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
        )
        keyboard.row(
            types.InlineKeyboardButton("💳 اشتراک‌ها", callback_data="admin_subs"),
            types.InlineKeyboardButton("📁 فایل‌ها", callback_data="admin_files"),
        )
        keyboard.row(
            types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        )
        if owner:
            keyboard.row(
                types.InlineKeyboardButton("👮 مدیریت ادمین‌ها", callback_data="owner_admins"),
                types.InlineKeyboardButton("⚙️ تنظیمات", callback_data="owner_settings"),
            )
    else:
        keyboard.row(
            types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            types.InlineKeyboardButton("👥 Users", callback_data="admin_users"),
        )
        keyboard.row(
            types.InlineKeyboardButton("💳 Subscriptions", callback_data="admin_subs"),
            types.InlineKeyboardButton("📁 Files", callback_data="admin_files"),
        )
        keyboard.row(
            types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        )
        if owner:
            keyboard.row(
                types.InlineKeyboardButton("👮 Manage admins", callback_data="owner_admins"),
                types.InlineKeyboardButton("⚙️ Settings", callback_data="owner_settings"),
            )
    keyboard.row(
        types.InlineKeyboardButton(
            "⬅️ بازگشت" if language == "fa" else "⬅️ Back",
            callback_data="admin_back"
        )
    )
    return keyboard


def admin_panel_text(language, owner=False):
    if language == "fa":
        return (
            "👑 پنل مالک" if owner else "🛡 پنل ادمین"
        ) + "\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید."
    return (
        "👑 Owner Panel" if owner else "🛡 Admin Panel"
    ) + "\n\nChoose an option below."


def send_admin_panel(chat_id, user_id):
    language = get_language(user_id)
    owner = int(user_id) == ADMIN_ID
    bot.send_message(
        chat_id,
        admin_panel_text(language, owner),
        reply_markup=admin_keyboard(language, owner),
    )


def send_admin_stats(chat_id, user_id):
    language = get_language(user_id)
    users = table_count("bot_users")
    files = table_count("files")
    downloads = table_count("downloads")
    admins = len(get_admin_ids())

    if language == "fa":
        text = (
            "📊 آمار ربات\n\n"
            f"👥 کاربران ثبت‌شده: {users}\n"
            f"📁 فایل‌ها: {files}\n"
            f"⬇️ دانلودها: {downloads}\n"
            f"👮 تعداد ادمین‌ها: {admins}"
        )
    else:
        text = (
            "📊 Bot Statistics\n\n"
            f"👥 Registered users: {users}\n"
            f"📁 Files: {files}\n"
            f"⬇️ Downloads: {downloads}\n"
            f"👮 Admins: {admins}"
        )
    bot.send_message(chat_id, text, reply_markup=admin_keyboard(language, int(user_id) == ADMIN_ID))


def send_admin_users(chat_id, user_id):
    language = get_language(user_id)
    ids = get_bot_user_ids(limit=100)
    preview = ids[:30]

    if language == "fa":
        text = f"👥 کاربران ثبت‌شده: {len(ids)}\n\n"
        text += "\n".join(f"• `{x}`" for x in preview) if preview else "هنوز کاربری ثبت نشده است."
        if len(ids) > 30:
            text += "\n\n... فقط ۳۰ مورد اول نمایش داده شد."
    else:
        text = f"👥 Registered users: {len(ids)}\n\n"
        text += "\n".join(f"• `{x}`" for x in preview) if preview else "No users registered yet."
        if len(ids) > 30:
            text += "\n\n... only the first 30 are shown."

    bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown",
        reply_markup=admin_keyboard(language, int(user_id) == ADMIN_ID),
    )


def send_admin_subs(chat_id, user_id):
    language = get_language(user_id)
    active = 0
    now = int(time.time())

    if supabase_enabled():
        try:
            url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/bot_users"
            response = requests.get(
                url,
                headers=supabase_headers(),
                params={
                    "select": "user_id,subscription_until",
                    "subscription_until": f"gt.{now}",
                    "limit": "5000",
                },
                timeout=10,
            )
            if response.ok:
                active = len(response.json() or [])
        except Exception as e:
            print("Subscriptions count error:", e)

    if language == "fa":
        text = f"💳 اشتراک‌های فعال: {active}"
    else:
        text = f"💳 Active subscriptions: {active}"

    bot.send_message(
        chat_id,
        text,
        reply_markup=admin_keyboard(language, int(user_id) == ADMIN_ID),
    )


def send_admin_files(chat_id, user_id):
    language = get_language(user_id)
    count = table_count("files")
    if language == "fa":
        text = f"📁 تعداد فایل‌های ثبت‌شده: {count}"
    else:
        text = f"📁 Stored files: {count}"

    bot.send_message(
        chat_id,
        text,
        reply_markup=admin_keyboard(language, int(user_id) == ADMIN_ID),
    )


def send_owner_admins(chat_id, user_id):
    language = get_language(user_id)
    ids = sorted(get_admin_ids())
    lines = []
    for admin_id in ids:
        role = "👑 مالک" if admin_id == ADMIN_ID else "🛡 ادمین"
        lines.append(f"{role}: `{admin_id}`")

    if language == "fa":
        text = "👮 مدیریت ادمین‌ها\n\n" + (
            "\n".join(lines) if lines else "ادمینی ثبت نشده است."
        ) + "\n\nبرای افزودن: /addadmin USER_ID\nبرای حذف: /deladmin USER_ID"
    else:
        text = "👮 Admin Management\n\n" + (
            "\n".join(lines) if lines else "No admins registered."
        ) + "\n\nAdd: /addadmin USER_ID\nRemove: /deladmin USER_ID"

    bot.send_message(
        chat_id,
        text,
        parse_mode="Markdown",
        reply_markup=admin_keyboard(language, True),
    )


def broadcast_message(owner_id, source_message):
    ids = get_bot_user_ids(limit=5000)
    sent = 0
    failed = 0

    for target_id in ids:
        if target_id == owner_id:
            continue
        try:
            bot.copy_message(
                target_id,
                source_message.chat.id,
                source_message.message_id,
            )
            sent += 1
        except Exception:
            failed += 1

    return sent, failed




# =========================
# Supabase
# =========================

def supabase_enabled():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def get_user(user_id):
    """اطلاعات کاربر را از Supabase می‌خواند."""
    if not supabase_enabled():
        return local_users.get(user_id, {})

    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/bot_users"
        params = {"user_id": f"eq.{user_id}", "limit": "1"}
        response = requests.get(
            url,
            headers=supabase_headers(),
            params=params,
            timeout=10
        )

        if response.ok and response.json():
            return response.json()[0]

    except Exception as e:
        print("Supabase get error:", e)

    return local_users.get(user_id, {})


def save_user(user_id, language=None, subscription_until=None, charge_id=None):
    """کاربر را در Supabase ثبت/به‌روزرسانی می‌کند."""
    old = get_user(user_id)

    data = {
        "user_id": user_id,
        "language": language if language else old.get("language", "en"),
        "subscription_until": (
            subscription_until
            if subscription_until is not None
            else old.get("subscription_until")
        ),
        "telegram_payment_charge_id": (
            charge_id
            if charge_id is not None
            else old.get("telegram_payment_charge_id")
        ),
        "updated_at": int(time.time())
    }

    local_users[user_id] = data

    if not supabase_enabled():
        return True

    try:
        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/bot_users"
        response = requests.post(
            url,
            headers={
                **supabase_headers(),
                "Prefer": "resolution=merge-duplicates,return=representation"
            },
            params={"on_conflict": "user_id"},
            json=data,
            timeout=10
        )
        return response.ok

    except Exception as e:
        print("Supabase save error:", e)
        return False


def get_language(user_id):
    user = get_user(user_id)
    return user.get("language", "en")


def is_subscribed(user_id):
    if is_admin(user_id):
        return True

    user = get_user(user_id)
    until = user.get("subscription_until")

    try:
        return until is not None and int(until) > int(time.time())
    except (TypeError, ValueError):
        return False


# =========================
# متن‌ها
# =========================

def language_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    return keyboard


def main_keyboard(language):
    keyboard = types.InlineKeyboardMarkup()

    if language == "fa":
        keyboard.row(
            types.InlineKeyboardButton("💳 خرید اشتراک", callback_data="subscribe"),
            types.InlineKeyboardButton("📅 وضعیت اشتراک", callback_data="status")
        )
        keyboard.row(
            types.InlineKeyboardButton("🌐 تغییر زبان", callback_data="change_language")
        )
    else:
        keyboard.row(
            types.InlineKeyboardButton("💳 Subscribe", callback_data="subscribe"),
            types.InlineKeyboardButton("📅 Subscription", callback_data="status")
        )
        keyboard.row(
            types.InlineKeyboardButton("🌐 Change language", callback_data="change_language")
        )

    return keyboard


def welcome_text(language):
    if language == "fa":
        return (
            "سلام! به ربات من خوش آمدید 🎉\n\n"
            "زبان شما روی فارسی تنظیم شد.\n\n"
            "برای استفاده از امکانات پولی، اشتراک ۳۰ روزه تهیه کنید."
        )

    return (
        "Hello! Welcome to my bot 🎉\n\n"
        "Your language has been set to English.\n\n"
        "Subscribe for 30 days to use the paid features."
    )


def subscription_text(language):
    if language == "fa":
        return (
            "⭐ اشتراک ۳۰ روزه\n\n"
            "قیمت: 250 Telegram Stars\n"
            "مدت: 30 روز\n\n"
            "با پرداخت، اشتراک شما فعال می‌شود."
        )

    return (
        "⭐ 30-Day Subscription\n\n"
        "Price: 250 Telegram Stars\n"
        "Duration: 30 days\n\n"
        "Your subscription will be activated after payment."
    )


def expired_text(language):
    if language == "fa":
        return (
            "⛔ اشتراک شما فعال نیست یا منقضی شده است.\n\n"
            "برای ادامه استفاده، اشتراک ۳۰ روزه تهیه کنید."
        )

    return (
        "⛔ Your subscription is inactive or expired.\n\n"
        "Please subscribe for 30 days to continue."
    )


def status_text(language, until):
    if until and int(until) > int(time.time()):
        remaining = int(until) - int(time.time())
        days = max(1, remaining // 86400)

        if language == "fa":
            return f"✅ اشتراک شما فعال است.\n\n⏳ حدود {days} روز باقی مانده است."

        return f"✅ Your subscription is active.\n\n⏳ About {days} days remaining."

    if language == "fa":
        return "❌ اشتراک شما فعال نیست."

    return "❌ Your subscription is not active."


# =========================
# اشتراک
# =========================

def send_subscription_invoice(chat_id):
    language = get_language(chat_id)

    try:
        prices = [types.LabeledPrice("30-Day Subscription", STAR_PRICE)]

        # اشتراک خودکار 30 روزه Telegram Stars
        invoice_link = bot.create_invoice_link(
            title="30-Day Subscription",
            description="30 days access to the bot",
            payload=f"subscription:{chat_id}",
            provider_token=None,
            currency="XTR",
            prices=prices,
            subscription_period=SUBSCRIPTION_SECONDS
        )

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "⭐ پرداخت / Pay",
                url=invoice_link
            )
        )

        if language == "fa":
            text = subscription_text(language)
        else:
            text = subscription_text(language)

        bot.send_message(chat_id, text, reply_markup=keyboard)

    except Exception as e:
        print("Invoice error:", e)

        if language == "fa":
            bot.send_message(
                chat_id,
                "❌ فعلاً امکان ساخت فاکتور وجود ندارد. "
                "لطفاً بعداً دوباره امتحان کنید."
            )
        else:
            bot.send_message(
                chat_id,
                "❌ I couldn't create the payment invoice right now. "
                "Please try again later."
            )


@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(query):
    # پرداخت دیجیتال Telegram Stars
    try:
        bot.answer_pre_checkout_query(query.id, ok=True)
    except Exception as e:
        print("Pre-checkout error:", e)


@bot.message_handler(content_types=["successful_payment"])
def successful_payment(message):
    payment = message.successful_payment
    user_id = message.from_user.id

    # Telegram برای اشتراک Stars تاریخ انقضا را می‌تواند برگرداند.
    expiration = getattr(payment, "subscription_expiration_date", None)

    if not expiration:
        expiration = int(time.time()) + SUBSCRIPTION_SECONDS

    charge_id = getattr(payment, "telegram_payment_charge_id", None)

    save_user(
        user_id=user_id,
        subscription_until=int(expiration),
        charge_id=charge_id
    )

    language = get_language(user_id)

    if language == "fa":
        bot.send_message(
            message.chat.id,
            "✅ پرداخت با موفقیت انجام شد!\n\n"
            "🎉 اشتراک ۳۰ روزه شما فعال شد."
        )
    else:
        bot.send_message(
            message.chat.id,
            "✅ Payment successful!\n\n"
            "🎉 Your 30-day subscription is now active."
        )


# =========================
# دستورات
# =========================

@bot.message_handler(commands=["start"])
def welcome(m):
    user_id = m.from_user.id
    user = get_user(user_id)

    if not user.get("language"):
        bot.reply_to(
            m,
            "🌐 Please choose your language / لطفاً زبان خود را انتخاب کنید:",
            reply_markup=language_keyboard()
        )
        return

    language = user.get("language", "en")

    bot.reply_to(
        m,
        welcome_text(language),
        reply_markup=main_keyboard(language)
    )


@bot.message_handler(commands=["admin", "panel"])
def admin_command(m):
    if not is_admin(m.from_user.id):
        language = get_language(m.from_user.id)
        bot.reply_to(
            m,
            "⛔ دسترسی ندارید." if language == "fa" else "⛔ Access denied."
        )
        return
    send_admin_panel(m.chat.id, m.from_user.id)


@bot.message_handler(commands=["addadmin"])
def add_admin_command(m):
    if m.from_user.id != ADMIN_ID:
        return

    parts = m.text.split(maxsplit=1)
    language = get_language(m.from_user.id)

    if len(parts) != 2 or not parts[1].strip().isdigit():
        bot.reply_to(
            m,
            "فرمت: /addadmin USER_ID" if language == "fa"
            else "Format: /addadmin USER_ID"
        )
        return

    target_id = int(parts[1].strip())
    if target_id == ADMIN_ID:
        bot.reply_to(m, "این کاربر خود مالک است." if language == "fa" else "This user is already the owner.")
        return

    if _admin_insert(target_id):
        bot.reply_to(
            m,
            f"✅ ادمین {target_id} اضافه شد." if language == "fa"
            else f"✅ Admin {target_id} added."
        )
    else:
        bot.reply_to(
            m,
            "❌ افزودن ادمین انجام نشد. ساختار جدول admins را بررسی کن."
            if language == "fa"
            else "❌ Could not add the admin. Please check the admins table schema."
        )


@bot.message_handler(commands=["deladmin"])
def del_admin_command(m):
    if m.from_user.id != ADMIN_ID:
        return

    parts = m.text.split(maxsplit=1)
    language = get_language(m.from_user.id)

    if len(parts) != 2 or not parts[1].strip().isdigit():
        bot.reply_to(
            m,
            "فرمت: /deladmin USER_ID" if language == "fa"
            else "Format: /deladmin USER_ID"
        )
        return

    target_id = int(parts[1].strip())
    if target_id == ADMIN_ID:
        bot.reply_to(
            m,
            "❌ مالک قابل حذف نیست." if language == "fa"
            else "❌ The owner cannot be removed."
        )
        return

    if _admin_delete(target_id):
        bot.reply_to(
            m,
            f"✅ ادمین {target_id} حذف شد." if language == "fa"
            else f"✅ Admin {target_id} removed."
        )
    else:
        bot.reply_to(
            m,
            "❌ حذف ادمین انجام نشد." if language == "fa"
            else "❌ Could not remove the admin."
        )


@bot.message_handler(commands=["broadcast"])
def broadcast_command(m):
    if not is_admin(m.from_user.id):
        return

    language = get_language(m.from_user.id)
    if not m.reply_to_message:
        bot.reply_to(
            m,
            "روی پیام موردنظر Reply بزن و /broadcast را ارسال کن."
            if language == "fa"
            else "Reply to the message you want to broadcast, then send /broadcast."
        )
        return

    sent, failed = broadcast_message(m.from_user.id, m.reply_to_message)
    bot.reply_to(
        m,
        f"📢 ارسال شد: {sent}\\n❌ ناموفق: {failed}"
        if language == "fa"
        else f"📢 Sent: {sent}\\n❌ Failed: {failed}"
    )


@bot.message_handler(commands=["language"])
def change_language_command(m):
    bot.send_message(
        m.chat.id,
        "🌐 Please choose your language / لطفاً زبان خود را انتخاب کنید:",
        reply_markup=language_keyboard()
    )


@bot.message_handler(commands=["subscribe"])
def subscribe_command(m):
    if is_admin(m.from_user.id):
        language = get_language(m.from_user.id)
        bot.send_message(
            m.chat.id,
            "👑 Admin access is always active." if language == "en"
            else "👑 دسترسی ادمین همیشه فعال است."
        )
        return

    if is_subscribed(m.from_user.id):
        language = get_language(m.from_user.id)
        user = get_user(m.from_user.id)
        bot.send_message(
            m.chat.id,
            status_text(language, user.get("subscription_until"))
        )
        return

    send_subscription_invoice(m.chat.id)


@bot.message_handler(commands=["status"])
def status_command(m):
    language = get_language(m.from_user.id)
    user = get_user(m.from_user.id)

    bot.send_message(
        m.chat.id,
        status_text(language, user.get("subscription_until")),
        reply_markup=main_keyboard(language)
    )


# =========================
# دکمه‌های زبان و منو
# =========================

@bot.callback_query_handler(
    func=lambda call: call.data.startswith("admin_")
    or call.data.startswith("owner_")
)
def admin_button_handler(call):
    user_id = call.from_user.id

    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "Access denied.", show_alert=True)
        return

    language = get_language(user_id)
    owner = user_id == ADMIN_ID
    data = call.data

    if data == "admin_back":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            welcome_text(language),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_keyboard(language),
        )
        return

    if data == "admin_stats":
        bot.answer_callback_query(call.id)
        send_admin_stats(call.message.chat.id, user_id)
        return

    if data == "admin_users":
        bot.answer_callback_query(call.id)
        send_admin_users(call.message.chat.id, user_id)
        return

    if data == "admin_subs":
        bot.answer_callback_query(call.id)
        send_admin_subs(call.message.chat.id, user_id)
        return

    if data == "admin_files":
        bot.answer_callback_query(call.id)
        send_admin_files(call.message.chat.id, user_id)
        return

    if data == "admin_broadcast":
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "📢 برای ارسال همگانی، روی پیام موردنظر Reply کن و /broadcast را بفرست."
            if language == "fa"
            else "📢 Reply to the message you want to broadcast and send /broadcast.",
        )
        return

    if data == "owner_admins":
        if not owner:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        send_owner_admins(call.message.chat.id, user_id)
        return

    if data == "owner_settings":
        if not owner:
            bot.answer_callback_query(call.id, "Owner only.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "⚙️ تنظیمات فعلاً شامل قیمت اشتراک و مدت اشتراک است.\n"
            f"⭐ قیمت: {STAR_PRICE} Stars\n"
            "📅 مدت: 30 روز\n\n"
            "برای تغییر قیمت متغیر STAR_PRICE را تغییر بده."
            if language == "fa"
            else
            "⚙️ Current settings:\n"
            f"⭐ Price: {STAR_PRICE} Stars\n"
            "📅 Duration: 30 days\n\n"
            "Change STAR_PRICE in the code to change the price.",
            reply_markup=admin_keyboard(language, True),
        )
        return

@bot.callback_query_handler(
    func=lambda call: call.data in [
        "lang_fa",
        "lang_en",
        "subscribe",
        "status",
        "change_language"
    ]
)
def button_handler(call):
    user_id = call.from_user.id

    if call.data == "lang_fa":
        save_user(user_id, language="fa")
        language = "fa"

        bot.answer_callback_query(call.id, "زبان فارسی ذخیره شد.")
        bot.edit_message_text(
            welcome_text(language),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_keyboard(language)
        )
        return

    if call.data == "lang_en":
        save_user(user_id, language="en")
        language = "en"

        bot.answer_callback_query(call.id, "English saved.")
        bot.edit_message_text(
            welcome_text(language),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_keyboard(language)
        )
        return

    language = get_language(user_id)

    if call.data == "change_language":
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "🌐 Please choose your language / لطفاً زبان خود را انتخاب کنید:",
            reply_markup=language_keyboard()
        )
        return

    if call.data == "status":
        user = get_user(user_id)
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            status_text(language, user.get("subscription_until")),
            reply_markup=main_keyboard(language)
        )
        return

    if call.data == "subscribe":
        bot.answer_callback_query(call.id)

        if user_id == ADMIN_ID:
            bot.send_message(
                call.message.chat.id,
                "👑 Admin access is always active." if language == "en"
                else "👑 دسترسی ادمین همیشه فعال است."
            )
            return

        if is_subscribed(user_id):
            user = get_user(user_id)
            bot.send_message(
                call.message.chat.id,
                status_text(language, user.get("subscription_until"))
            )
            return

        send_subscription_invoice(call.message.chat.id)


# =========================
# پیام‌های عادی
# =========================

@bot.message_handler(func=lambda m: True)
def check_id(m):
    user_id = m.from_user.id
    language = get_language(user_id)

    # مالک و ادمین بدون اشتراک دسترسی مدیریتی دارند.
    if is_admin(user_id):
        send_admin_panel(m.chat.id, user_id)
        return

    # کاربران عادی باید اشتراک فعال داشته باشند.
    if not is_subscribed(user_id):
        bot.reply_to(
            m,
            expired_text(language),
            reply_markup=main_keyboard(language)
        )
        return

    if language == "fa":
        bot.reply_to(m, f"کد کاربری شما: {user_id}")
    else:
        bot.reply_to(m, f"Your code: {user_id}")


# =========================
# Render Web Service
# =========================
# Render Web Service باید حداقل روی یک پورت HTTP گوش بدهد.
# این سرور سبک فقط برای Health Check و Port Binding است
# و منطق اصلی ربات را تغییر نمی‌دهد.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

PORT = int(os.getenv("PORT", "10000"))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # لاگ‌های اضافی Health Check را نمایش نده.
        return


def start_health_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server is running on port {PORT}...")
    server.serve_forever()


threading.Thread(target=start_health_server, daemon=True).start()

print("bot is on...")
bot.infinity_polling()
