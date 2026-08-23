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
    if user_id == ADMIN_ID:
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


@bot.message_handler(commands=["language"])
def change_language_command(m):
    bot.send_message(
        m.chat.id,
        "🌐 Please choose your language / لطفاً زبان خود را انتخاب کنید:",
        reply_markup=language_keyboard()
    )


@bot.message_handler(commands=["subscribe"])
def subscribe_command(m):
    if m.from_user.id == ADMIN_ID:
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

    # ادمین بدون اشتراک دسترسی کامل دارد.
    if user_id == ADMIN_ID:
        if language == "fa":
            bot.reply_to(m, "سلام ادمین 👑")
        else:
            bot.reply_to(m, "Hello admin 👑")
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
