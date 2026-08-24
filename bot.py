import os
import threading
import time
import requests
import telebot
from http.server import BaseHTTPRequestHandler, HTTPServer
from telebot import types

TOKEN = "8915241769:AAHdKt2H-zUm8GavaWONoc-FfaTyGV_vhTo"
bot = telebot.TeleBot(TOKEN)

# زبان انتخابی هر کاربر
user_languages = {}


# ============================================================
# COMPATIBILITY / RENDER / SUPABASE HELPERS
# These helpers are added without removing or changing the
# existing bot handlers and features.
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "6914909647"))


def supabase_enabled():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def get_language(user_id):
    return user_languages.get(user_id, "en")


def owner_only(user_id):
    return int(user_id) == OWNER_ID


def save_user(user_id, **fields):
    # Keep the existing subscription feature working when Supabase
    # is configured, while remaining safe when it is not configured.
    if not supabase_enabled():
        return False

    payload = {"user_id": int(user_id), **fields}
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/users"

    try:
        headers = {
            **supabase_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return r.ok
    except Exception as e:
        print("save_user error:", e)
        return False



def language_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
        types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    return keyboard


@bot.message_handler(commands=['start'])
def welcome(m):
    bot.reply_to(
        m,
        "🌐 Please choose your language / لطفاً زبان خود را انتخاب کنید:",
        reply_markup=language_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data in ['lang_fa', 'lang_en'])
def choose_language(call):
    if call.data == "lang_fa":
        user_languages[call.from_user.id] = "fa"
        text = "سلام! به ربات من خوش آمدید 🎉\nزبان شما روی فارسی تنظیم شد."
    else:
        user_languages[call.from_user.id] = "en"
        text = "Hello! Welcome to my bot 🎉\nYour language has been set to English."

    bot.answer_callback_query(call.id, "Language saved!")
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id
    )


@bot.message_handler(func=lambda m: True)
def check_id(m):
    language = user_languages.get(m.from_user.id, "en")

    if m.from_user.id == 6914909647:
        if language == "fa":
            bot.reply_to(m, "سلام ادمین 👑")
        else:
            bot.reply_to(m, "Hello admin 👑")
    else:
        if language == "fa":
            bot.reply_to(m, f"کد کاربری شما: {m.from_user.id}")
        else:
            bot.reply_to(m, f"Your code: {m.from_user.id}")


@bot.callback_query_handler(func=lambda c: c.data in ("osub_open","oexp_open"))
def owner_management_open(call):
    if not owner_only(call.from_user.id):
        bot.answer_callback_query(call.id, "Only owner.", show_alert=True); return
    bot.answer_callback_query(call.id)
    if call.data == "osub_open":
        owner_subscription_manager(call.message.chat.id, call.from_user.id)
    else:
        owner_expire_manager(call.message.chat.id, call.from_user.id)

@bot.message_handler(commands=["language"])
def language_command_restored(m):
    k = types.InlineKeyboardMarkup()
    k.row(types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
          types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"))
    bot.send_message(m.chat.id, "🌐 زبان ربات را انتخاب کنید / Choose bot language:", reply_markup=k)


# ============================================================
# SINGLE OWNER SUBSCRIPTION + FILE EXPIRATION MANAGEMENT
# ============================================================
OWNER_PLAN_CATALOG = {
    "free_3d": {"days": 3, "title_fa": "رایگان ۳ روزه", "title_en": "Free 3 days"},
    "stars_30d": {"days": 30, "title_fa": "۳۰ روزه - ۲۵۰ ⭐", "title_en": "30 days - 250 ⭐"},
    "stars_90d": {"days": 90, "title_fa": "۹۰ روزه - ۶۵۰ ⭐", "title_en": "90 days - 650 ⭐"},
    "stars_365d": {"days": 365, "title_fa": "۱ ساله - ۲۰۰۰ ⭐", "title_en": "1 year - 2000 ⭐"},
}
_OWNER_STATE = {}

def _owner_setting_get(key, default=30):
    if not supabase_enabled(): return default
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/settings"
    for col in ("key","name","setting"):
        try:
            r = requests.get(url, headers=supabase_headers(),
                             params={"select":"*", col:f"eq.{key}", "limit":"1"}, timeout=10)
            if r.ok and r.json(): return r.json()[0].get("value", default)
        except Exception: pass
    return default

def _owner_setting_set(key, value):
    if not supabase_enabled(): return False
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/settings"
    headers = {**supabase_headers(), "Prefer":"resolution=merge-duplicates,return=minimal"}
    for payload in ({"key":key,"value":str(value)}, {"name":key,"value":str(value)}, {"setting":key,"value":str(value)}):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=10)
            if r.ok: return True
        except Exception: pass
    return False

def owner_subscription_manager(chat_id, owner_id):
    lang = get_language(owner_id)
    k = types.InlineKeyboardMarkup()
    plans = [
        ("🆓 رایگان ۳ روزه" if lang=="fa" else "🆓 Free 3 days", "osub_free_3d"),
        ("⭐ ۳۰ روزه - ۲۵۰" if lang=="fa" else "⭐ 30 days - 250", "osub_stars_30d"),
        ("⭐ ۹۰ روزه - ۶۵۰" if lang=="fa" else "⭐ 90 days - 650", "osub_stars_90d"),
        ("⭐ ۱ ساله - ۲۰۰۰" if lang=="fa" else "⭐ 1 year - 2000", "osub_stars_365d"),
    ]
    for label, data in plans: k.add(types.InlineKeyboardButton(label, callback_data=data))
    bot.send_message(chat_id,
        "💳 مدیریت اشتراک\nنوع اشتراک را انتخاب کن؛ سپس شناسه کاربر را بفرست."
        if lang=="fa" else
        "💳 Subscription management\nChoose a plan, then send the user's Telegram ID.",
        reply_markup=k)

def owner_expire_manager(chat_id, owner_id):
    lang = get_language(owner_id)
    try: current = int(_owner_setting_get("file_expire_days", 30))
    except Exception: current = 30
    k = types.InlineKeyboardMarkup()
    for d in (1,3,7,30):
        k.add(types.InlineKeyboardButton(f"{d} روز" if lang=="fa" else f"{d} days", callback_data=f"oexp_{d}"))
    k.add(types.InlineKeyboardButton("⏱ زمان دلخواه" if lang=="fa" else "⏱ Custom time", callback_data="oexp_custom"))
    bot.send_message(chat_id,
        f"⏱ زمان فعلی حذف فایل: {current} روز\nمدت جدید را انتخاب کن:"
        if lang=="fa" else
        f"⏱ Current file deletion time: {current} days\nChoose the new duration:",
        reply_markup=k)

@bot.callback_query_handler(func=lambda c: c.data.startswith("osub_") or c.data.startswith("oexp_"))
def owner_management_callbacks_final(call):
    uid = call.from_user.id
    if not owner_only(uid):
        bot.answer_callback_query(call.id, "Only owner.", show_alert=True); return
    lang = get_language(uid); data = call.data; bot.answer_callback_query(call.id)
    if data.startswith("osub_"):
        plan = OWNER_PLAN_CATALOG.get(data[5:])
        if plan:
            _OWNER_STATE[uid] = data[5:]
            bot.send_message(call.message.chat.id,
                "شناسه عددی کاربر را بفرست:" if lang=="fa" else "Send the user's numeric Telegram ID:")
        return
    if data.startswith("oexp_"):
        value = data[5:]
        if value == "custom":
            _OWNER_STATE[uid] = "expire_custom"
            bot.send_message(call.message.chat.id,
                "تعداد روز را بفرست (مثلاً 14):" if lang=="fa" else "Send days (e.g. 14):")
            return
        days = int(value)
        if _owner_setting_set("file_expire_days", days):
            bot.send_message(call.message.chat.id,
                f"✅ زمان حذف فایل‌ها روی {days} روز تنظیم شد."
                if lang=="fa" else f"✅ File deletion time set to {days} days.")
        else: bot.send_message(call.message.chat.id, "❌ ذخیره تنظیمات ناموفق بود.")

@bot.message_handler(func=lambda m: m.from_user.id in _OWNER_STATE)
def owner_management_input_final(m):
    uid = m.from_user.id
    if not owner_only(uid):
        _OWNER_STATE.pop(uid,None); return
    state = _OWNER_STATE.get(uid); lang = get_language(uid)
    if state == "expire_custom":
        try:
            days = int(m.text.strip())
            if not (1 <= days <= 3650) or not _owner_setting_set("file_expire_days", days): raise ValueError
            _OWNER_STATE.pop(uid,None)
            bot.reply_to(m, f"✅ زمان حذف فایل روی {days} روز تنظیم شد." if lang=="fa" else f"✅ File deletion time set to {days} days.")
        except Exception: bot.reply_to(m, "❌ عدد نامعتبر است.")
        return
    plan = OWNER_PLAN_CATALOG.get(state)
    if plan:
        try:
            target = int(m.text.strip())
            until = int(time.time()) + plan["days"]*86400
            save_user(target, subscription_until=until)
            _OWNER_STATE.pop(uid,None)
            bot.reply_to(m, f"✅ {plan['title_fa']} برای {target} فعال شد." if lang=="fa" else f"✅ {plan['title_en']} activated for {target}.")
        except Exception: bot.reply_to(m, "❌ شناسه کاربر نامعتبر است.")



# ============================================================
# RENDER WEBHOOK / HEALTH SERVER
# Keeps the existing bot handlers and adds Telegram webhook support.
# Set WEBHOOK_URL in Render to the service URL (e.g. https://your-service.onrender.com).
# If WEBHOOK_URL is absent, the bot safely falls back to polling.
# ============================================================
WEBHOOK_URL = (os.getenv("WEBHOOK_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()).rstrip("/")
PORT = int(os.getenv("PORT", "10000"))

class _WebhookHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") != "/telegram/webhook":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            update = types.Update.de_json(raw.decode("utf-8"))
            if update:
                bot.process_new_updates([update])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print("Webhook update error:", e)
            self.send_response(500)
            self.end_headers()

def _start_web_server():
    server = HTTPServer(("0.0.0.0", PORT), _WebhookHandler)
    print(f"HTTP server listening on {PORT}")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server

def _configure_telegram_webhook():
    if not WEBHOOK_URL:
        return False
    url = WEBHOOK_URL + "/telegram/webhook"
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=url, drop_pending_updates=False)
        print("Telegram webhook configured:", url)
        return True
    except Exception as e:
        print("Webhook setup error:", e)
        return False



try:
    bot.set_my_commands([
        types.BotCommand("start", "شروع / Start"),
        types.BotCommand("language", "زبان / Language"),
        types.BotCommand("subscribe", "اشتراک / Subscribe"),
        types.BotCommand("status", "وضعیت اشتراک / Status"),
        types.BotCommand("panel", "پنل مدیریت / Admin panel"),
    ])
except Exception as e:
    print("Command menu setup error:", e)

print("bot is on...")
_start_web_server()
if _configure_telegram_webhook():
    # Webhook mode: Telegram pushes updates to Render, so a sleeping instance
    # can be activated by an incoming HTTP request when the platform wakes it.
    while True:
        time.sleep(3600)
else:
    # Existing behavior remains available if WEBHOOK_URL is not configured.
    bot.infinity_polling()


# ============================================================
# ADDITIONS FROM bot_render_webhook(1).py — NOTHING FROM THE ORIGINAL FILE WAS REMOVED
# ============================================================
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None
from flask import Flask, request
from datetime import datetime, timedelta
import secrets

# =========================
# Flask Keep-Alive / Health Server
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!", 200

@app.route("/health")
def health():
    return "OK", 200


# =========================
# Telegram Webhook
# =========================
# Render Free services sleep after inactivity. Telegram polling cannot wake
# a sleeping Render service because polling requires the Python process to
# already be running. Webhook mode fixes this: Telegram sends the user's
# update as an HTTP request, which wakes the Render Web Service.
WEBHOOK_PATH = "/telegram-webhook"
WEBHOOK_URL = WEBHOOK_URL or os.environ.get("RENDER_EXTERNAL_URL", "").strip()
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")


@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    if WEBHOOK_SECRET:
        incoming_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming_secret != WEBHOOK_SECRET:
            return "Forbidden", 403

    try:
        if not request.is_json:
            return "Bad Request", 400

        update = telebot.types.Update.de_json(request.get_json())
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as error:
        print("خطای webhook:", error)
        return "OK", 200


def setup_telegram_webhook():
    """
    Configure Telegram to deliver updates to this Render Web Service.
    On Render, RENDER_EXTERNAL_URL is provided automatically.
    WEBHOOK_URL can be set manually when running somewhere else.
    """
    if not WEBHOOK_URL:
        print("WEBHOOK_URL/RENDER_EXTERNAL_URL پیدا نشد؛ webhook فعال نشد.")
        return False

    try:
        bot.remove_webhook()
        time.sleep(0.2)

        kwargs = {}
        if WEBHOOK_SECRET:
            kwargs["secret_token"] = WEBHOOK_SECRET

        full_url = WEBHOOK_URL.rstrip("/") + WEBHOOK_PATH
        bot.set_webhook(url=full_url, **kwargs)

        print("Telegram webhook فعال شد:", full_url)
        return True
    except Exception as error:
        print("خطا در فعال‌سازی Telegram webhook:", error)
        return False


def run_flask():
    # Hosting services such as Render/Railway normally provide PORT.
    # 8000 is used locally if PORT is not defined.
    try:
        port = int(os.environ.get("PORT", "8000"))
    except (TypeError, ValueError):
        port = 8000

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )




# =========================
# تنظیمات اصلی
# =========================

# Existing BOT_TOKEN/OWNER_ID/bot from the original file are preserved and reused.

DEFAULT_DELETE_AFTER = 17

DEFAULT_SUB_DAYS = 30


# =========================
# Database support from the Render version
# =========================

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required.")

db_lock = threading.RLock()

user_states = {}
pending_downloads = {}

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def date_text(date_obj):
    return date_obj.strftime("%Y-%m-%d %H:%M:%S")

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    # SQLite '?' placeholders are converted to PostgreSQL '%s'.
    query = query.replace("?", "%s")
    with db_lock:
        connection = get_db()
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(query, params)
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            else:
                result = None
                if cursor.description:
                    row = cursor.fetchone()
                    result = row["id"] if row and "id" in row else None
            if commit:
                connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

def init_database():
    with db_lock:
        connection = get_db()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    name TEXT,
                    created_at TEXT NOT NULL,
                    expire_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id BIGSERIAL PRIMARY KEY,
                    admin_id BIGINT NOT NULL,
                    file_id TEXT NOT NULL,
                    file_name TEXT,
                    file_type TEXT NOT NULL,
                    caption TEXT,
                    token TEXT UNIQUE NOT NULL,
                    downloads INTEGER NOT NULL DEFAULT 0,
                    upload_date TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id BIGSERIAL PRIMARY KEY,
                    admin_id BIGINT NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_username TEXT,
                    channel_link TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id BIGSERIAL PRIMARY KEY,
                    file_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    admin_id BIGINT PRIMARY KEY,
                    delete_after INTEGER NOT NULL DEFAULT 60
                )
            """)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()


# =========================
# توابع دسترسی و منوها
# =========================

def is_owner(user_id):
    return user_id == OWNER_ID


def get_admin(user_id):
    return execute(
        "SELECT * FROM admins WHERE user_id = ?",
        (user_id,),
        fetchone=True
    )


def is_admin(user_id):
    admin = get_admin(user_id)

    if not admin:
        return False

    if admin["status"] != "active":
        return False

    try:
        expire_at = datetime.strptime(admin["expire_at"], "%Y-%m-%d %H:%M:%S")
        return expire_at > datetime.now()
    except Exception:
        return False


def get_active_admin(user_id):
    if not is_admin(user_id):
        return None
    return get_admin(user_id)


def admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("📤 آپلود فایل", "📂 فایل‌های من")
    keyboard.row("📊 آمار من", "📢 مدیریت کانال‌ها")
    keyboard.row("⏱ تنظیم حذف خودکار", "💳 وضعیت اشتراک")
    keyboard.row("❌ بستن پنل")
    return keyboard


def owner_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("👥 مدیریت ادمین‌ها", "➕ افزودن ادمین")
    keyboard.row("➖ حذف ادمین", "💰 درآمد")
    keyboard.row("📊 آمار کل", "📂 همه فایل‌ها")
    keyboard.row("❌ بستن پنل")
    return keyboard


def inline_button(text, callback_data):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text, callback_data=callback_data))
    return keyboard


def clear_state(user_id):
    user_states.pop(user_id, None)


def safe_send(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception:
        return None


# =========================
# دستورهای عمومی
# =========================

@bot.message_handler(commands=["start"])
def start_handler(message):
    user_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    if len(args) > 1 and args[1].startswith("file_"):
        token = args[1][5:]
        request_file(message, token)
        return

    if is_owner(user_id):
        bot.send_message(
            message.chat.id,
            "👑 به پنل مالک خوش آمدید.\nبرای ورود به پنل از /owner استفاده کنید."
        )
    elif is_admin(user_id):
        bot.send_message(
            message.chat.id,
            "🛠 شما ادمین هستید.\nبرای ورود به پنل از /panel استفاده کنید."
        )
    else:
        bot.send_message(
            message.chat.id,
            "سلام!\nاین ربات برای دریافت فایل استفاده می‌شود.\n"
            "لطفاً لینک فایل را از فرستنده دریافت کنید."
        )


@bot.message_handler(commands=["panel"])
def panel_handler(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        bot.send_message(
            message.chat.id,
            "⛔ شما دسترسی ادمین ندارید."
        )
        return

    clear_state(user_id)
    bot.send_message(
        message.chat.id,
        "🛠 پنل مدیریت ادمین:",
        reply_markup=admin_keyboard()
    )


@bot.message_handler(commands=["owner"])
def owner_handler(message):
    if not is_owner(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ فقط مالک به این بخش دسترسی دارد.")
        return

    clear_state(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "👑 پنل مالک:",
        reply_markup=owner_keyboard()
    )


# =========================
# دریافت فایل از لینک
# =========================

def request_file(message, token):
    user_id = message.from_user.id

    file_row = execute(
        "SELECT * FROM files WHERE token = ? AND deleted = 0",
        (token,),
        fetchone=True
    )

    if not file_row:
        bot.send_message(message.chat.id, "❌ لینک فایل نامعتبر یا منقضی شده است.")
        return

    admin = execute(
        "SELECT * FROM admins WHERE user_id = ?",
        (file_row["admin_id"],),
        fetchone=True
    )

    if not admin or not is_admin(admin["user_id"]):
        bot.send_message(
            message.chat.id,
            "❌ اشتراک صاحب این فایل منقضی شده یا فایل غیرفعال است."
        )
        return

    channels = execute(
        "SELECT * FROM channels WHERE admin_id = ?",
        (admin["user_id"],),
        fetchall=True
    )

    not_joined = []

    for channel in channels:
        try:
            member = bot.get_chat_member(channel["channel_id"], user_id)

            if member.status in ("left", "kicked"):
                not_joined.append(channel)

        except Exception:
            not_joined.append(channel)

    if not_joined:
        pending_downloads[user_id] = token

        keyboard = types.InlineKeyboardMarkup()

        for channel in not_joined:
            link = channel["channel_link"]

            if not link and channel["channel_username"]:
                username = channel["channel_username"].lstrip("@")
                link = "https://t.me/" + username

            if link:
                keyboard.add(
                    types.InlineKeyboardButton(
                        "📢 ورود به کانال",
                        url=link
                    )
                )

        keyboard.add(
            types.InlineKeyboardButton(
                "✅ عضو شدم",
                callback_data="check_join"
            )
        )

        bot.send_message(
            message.chat.id,
            "⚠️ برای دریافت فایل ابتدا عضو کانال شوید.",
            reply_markup=keyboard
        )
        return

    send_file_to_user(message.chat.id, message.from_user, file_row)


def send_file_to_user(chat_id, user, file_row):
    try:
        caption = file_row["caption"] or ""
        sent_message = None

        if file_row["file_type"] == "document":
            sent_message = bot.send_document(
                chat_id,
                file_row["file_id"],
                caption=caption
            )

        elif file_row["file_type"] == "photo":
            sent_message = bot.send_photo(
                chat_id,
                file_row["file_id"],
                caption=caption
            )

        elif file_row["file_type"] == "video":
            sent_message = bot.send_video(
                chat_id,
                file_row["file_id"],
                caption=caption
            )

        elif file_row["file_type"] == "audio":
            sent_message = bot.send_audio(
                chat_id,
                file_row["file_id"],
                caption=caption
            )

        elif file_row["file_type"] == "voice":
            sent_message = bot.send_voice(
                chat_id,
                file_row["file_id"],
                caption=caption
            )

        else:
            sent_message = bot.send_document(
                chat_id,
                file_row["file_id"],
                caption=caption
            )

        execute(
            "UPDATE files SET downloads = downloads + 1 WHERE id = ?",
            (file_row["id"],),
            commit=True
        )

        execute(
            """
            INSERT INTO downloads
            (file_id, user_id, username, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                file_row["id"],
                user.id,
                user.username or "",
                now_text()
            ),
            commit=True
        )

        admin = execute(
            "SELECT delete_after FROM settings WHERE admin_id = ?",
            (file_row["admin_id"],),
            fetchone=True
        )

        delete_after = (
            admin["delete_after"]
            if admin else DEFAULT_DELETE_AFTER
        )

        notice = bot.send_message(
            chat_id,
            f"✅ فایل ارسال شد\n⏱ این فایل تا {delete_after} ثانیه دیگر حذف خواهد شد"
        )

        if sent_message:
            thread = threading.Thread(
                target=delete_messages_later,
                args=(chat_id, sent_message.message_id, notice.message_id, delete_after),
                daemon=True
            )
            thread.start()

    except Exception:
        bot.send_message(
            chat_id,
            "❌ ارسال فایل با خطا مواجه شد."
        )


def delete_messages_later(chat_id, file_message_id, notice_message_id, seconds):
    try:
        time.sleep(seconds)

        try:
            bot.delete_message(chat_id, file_message_id)
        except Exception:
            pass

        try:
            bot.delete_message(chat_id, notice_message_id)
        except Exception:
            pass

        bot.send_message(chat_id, "🗑 فایل حذف شد")

    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join_callback(call):
    user_id = call.from_user.id
    token = pending_downloads.get(user_id)

    if not token:
        bot.answer_callback_query(
            call.id,
            "لینک دریافت پیدا نشد.",
            show_alert=True
        )
        return

    file_row = execute(
        "SELECT * FROM files WHERE token = ? AND deleted = 0",
        (token,),
        fetchone=True
    )

    if not file_row:
        bot.answer_callback_query(
            call.id,
            "فایل دیگر موجود نیست.",
            show_alert=True
        )
        return

    channels = execute(
        "SELECT * FROM channels WHERE admin_id = ?",
        (file_row["admin_id"],),
        fetchall=True
    )

    for channel in channels:
        try:
            member = bot.get_chat_member(
                channel["channel_id"],
                user_id
            )

            if member.status in ("left", "kicked"):
                bot.answer_callback_query(
                    call.id,
                    "هنوز در همه کانال‌ها عضو نشده‌اید.",
                    show_alert=True
                )
                return

        except Exception:
            bot.answer_callback_query(
                call.id,
                "عضویت شما قابل بررسی نیست.",
                show_alert=True
            )
            return

    pending_downloads.pop(user_id, None)

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    send_file_to_user(call.message.chat.id, call.from_user, file_row)


# =========================
# دریافت فایل توسط ادمین
# =========================

@bot.message_handler(content_types=[
    "document",
    "photo",
    "video",
    "audio",
    "voice"
])
def upload_handler(message):
    user_id = message.from_user.id

    if user_states.get(user_id, {}).get("action") != "upload":
        return

    if not is_admin(user_id):
        clear_state(user_id)
        bot.send_message(message.chat.id, "⛔ اشتراک شما فعال نیست.")
        return

    file_id = None
    file_name = ""
    file_type = "document"

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "document"
        file_type = "document"

    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
        file_type = "photo"

    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        file_type = "video"

    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
        file_type = "audio"

    elif message.voice:
        file_id = message.voice.file_id
        file_name = "voice.ogg"
        file_type = "voice"

    if not file_id:
        bot.send_message(message.chat.id, "❌ نوع فایل پشتیبانی نمی‌شود.")
        return

    caption = message.caption or ""

    token = secrets.token_urlsafe(8)

    while execute(
        "SELECT id FROM files WHERE token = ?",
        (token,),
        fetchone=True
    ):
        token = secrets.token_urlsafe(8)

    file_db_id = execute(
        """
        INSERT INTO files
        (admin_id, file_id, file_name, file_type, caption, token, upload_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            user_id,
            file_id,
            file_name,
            file_type,
            caption,
            token,
            now_text()
        ),
        commit=True
    )

    username = bot.get_me().username
    link = f"https://t.me/{username}?start=file_{token}"

    clear_state(user_id)

    bot.send_message(
        message.chat.id,
        f"✅ فایل ذخیره شد.\n\n"
        f"📄 نام: <code>{file_name}</code>\n"
        f"🔗 لینک اختصاصی:\n{link}\n\n"
        f"🆔 شناسه فایل: {file_db_id}",
        reply_markup=admin_keyboard()
    )


# =========================
# پنل ادمین
# =========================

@bot.message_handler(func=lambda message: True)
def text_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "❌ بستن پنل":
        clear_state(user_id)
        bot.send_message(
            message.chat.id,
            "پنل بسته شد.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    if text == "📤 آپلود فایل":
        if not is_admin(user_id):
            bot.send_message(message.chat.id, "⛔ اشتراک شما فعال نیست.")
            return

        user_states[user_id] = {"action": "upload"}
        bot.send_message(
            message.chat.id,
            "📤 فایل را ارسال کنید.\n"
            "فرمت‌های PDF، ZIP، MP4، MP3، عکس، وویس و سایر فایل‌ها پشتیبانی می‌شوند."
        )
        return

    if text == "📂 فایل‌های من":
        show_admin_files(message)
        return

    if text == "📊 آمار من":
        show_admin_stats(message)
        return

    if text == "📢 مدیریت کانال‌ها":
        channel_management(message)
        return

    if text == "⏱ تنظیم حذف خودکار":
        if not is_admin(user_id):
            bot.send_message(message.chat.id, "⛔ دسترسی ندارید.")
            return

        user_states[user_id] = {"action": "delete_after"}
        bot.send_message(
            message.chat.id,
            f"مدت حذف خودکار را بر حسب ثانیه ارسال کنید.\n"
            f"مقدار فعلی پیش‌فرض: {DEFAULT_DELETE_AFTER}"
        )
        return

    if text == "💳 وضعیت اشتراک":
        show_subscription(message)
        return

    if text == "👥 مدیریت ادمین‌ها":
        show_admins(message)
        return

    if text == "➕ افزودن ادمین":
        if is_owner(user_id):
            user_states[user_id] = {"action": "add_admin"}
            bot.send_message(message.chat.id, "آیدی عددی کاربر را ارسال کنید.")
        return

    if text == "➖ حذف ادمین":
        if is_owner(user_id):
            user_states[user_id] = {"action": "remove_admin"}
            bot.send_message(message.chat.id, "آیدی عددی ادمین را ارسال کنید.")
        return

    if text == "💰 درآمد":
        if is_owner(user_id):
            bot.send_message(
                message.chat.id,
                "💰 درآمد کل:\n"
                "برای ثبت درآمد واقعی، درگاه پرداخت باید به ربات متصل شود.\n"
                "در حال حاضر درآمد ثبت‌شده: 0"
            )
        return

    if text == "📊 آمار کل":
        if is_owner(user_id):
            show_global_stats(message)
        return

    if text == "📂 همه فایل‌ها":
        if is_owner(user_id):
            show_all_files(message)
        return

    state = user_states.get(user_id)

    if state:
        process_state(message, state)
        return


# =========================
# عملیات ادمین
# =========================

def show_admin_files(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ دسترسی ندارید.")
        return

    files = execute(
        """
        SELECT * FROM files
        WHERE admin_id = ? AND deleted = 0
        ORDER BY id DESC
        """,
        (message.from_user.id,),
        fetchall=True
    )

    if not files:
        bot.send_message(message.chat.id, "📂 هنوز فایلی آپلود نکرده‌اید.")
        return

    for item in files:
        bot.send_message(
            message.chat.id,
            f"📄 <b>{item['file_name']}</b>\n"
            f"⬇️ دانلود: {item['downloads']}\n"
            f"📅 آپلود: {item['upload_date']}\n"
            f"🔗 توکن: <code>{item['token']}</code>",
            reply_markup=types.InlineKeyboardMarkup(
                keyboard=[
                    [
                        types.InlineKeyboardButton(
                            "🗑 حذف",
                            callback_data=f"delete_file:{item['id']}"
                        ),
                        types.InlineKeyboardButton(
                            "✏️ ویرایش کپشن",
                            callback_data=f"edit_caption:{item['id']}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            "📊 آمار دانلود",
                            callback_data=f"file_stats:{item['id']}"
                        )
                    ]
                ]
            )
        )


def show_admin_stats(message):
    admin_id = message.from_user.id

    if not is_admin(admin_id):
        bot.send_message(message.chat.id, "⛔ دسترسی ندارید.")
        return

    files = execute(
        "SELECT COUNT(*) AS total FROM files WHERE admin_id = ? AND deleted = 0",
        (admin_id,),
        fetchone=True
    )

    downloads = execute(
        """
        SELECT COUNT(*) AS total
        FROM downloads d
        JOIN files f ON f.id = d.file_id
        WHERE f.admin_id = ?
        """,
        (admin_id,),
        fetchone=True
    )

    bot.send_message(
        message.chat.id,
        f"📊 آمار شما:\n\n"
        f"📂 تعداد فایل‌ها: {files['total']}\n"
        f"⬇️ تعداد دانلودها: {downloads['total']}"
    )


def show_subscription(message):
    admin = get_admin(message.from_user.id)

    if not admin:
        bot.send_message(message.chat.id, "⛔ ادمین نیستید.")
        return

    bot.send_message(
        message.chat.id,
        f"💳 وضعیت اشتراک: {admin['status']}\n"
        f"📅 تاریخ پایان: {admin['expire_at']}"
    )


def channel_management(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ دسترسی ندارید.")
        return

    channels = execute(
        "SELECT * FROM channels WHERE admin_id = ?",
        (message.from_user.id,),
        fetchall=True
    )

    text = "📢 کانال‌های اجباری:\n\n"

    if not channels:
        text += "هیچ کانالی ثبت نشده است."
    else:
        for channel in channels:
            text += (
                f"🆔 {channel['channel_id']}\n"
                f"🔗 {channel['channel_link'] or '-'}\n\n"
            )

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "➕ افزودن کانال",
            callback_data="add_channel"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "🗑 حذف همه کانال‌ها",
            callback_data="clear_channels"
        )
    )

    bot.send_message(message.chat.id, text, reply_markup=keyboard)


# =========================
# عملیات مالک
# =========================

def show_admins(message):
    admins = execute(
        "SELECT * FROM admins ORDER BY id DESC",
        fetchall=True
    )

    if not admins:
        bot.send_message(message.chat.id, "هیچ ادمینی ثبت نشده است.")
        return

    text = "👥 لیست ادمین‌ها:\n\n"

    for admin in admins:
        file_count = execute(
            """
            SELECT COUNT(*) AS total
            FROM files
            WHERE admin_id = ? AND deleted = 0
            """,
            (admin["user_id"],),
            fetchone=True
        )

        download_count = execute(
            """
            SELECT COUNT(*) AS total
            FROM downloads d
            JOIN files f ON f.id = d.file_id
            WHERE f.admin_id = ?
            """,
            (admin["user_id"],),
            fetchone=True
        )

        text += (
            f"👤 {admin['name'] or '-'}\n"
            f"🆔 {admin['user_id']}\n"
            f"📅 پایان: {admin['expire_at']}\n"
            f"📂 فایل‌ها: {file_count['total']}\n"
            f"⬇️ دانلودها: {download_count['total']}\n"
            f"📌 وضعیت: {admin['status']}\n\n"
        )

    bot.send_message(message.chat.id, text)


def show_global_stats(message):
    users = execute(
        "SELECT COUNT(DISTINCT user_id) AS total FROM downloads",
        fetchone=True
    )

    downloads = execute(
        "SELECT COUNT(*) AS total FROM downloads",
        fetchone=True
    )

    files = execute(
        "SELECT COUNT(*) AS total FROM files WHERE deleted = 0",
        fetchone=True
    )

    admins = execute(
        "SELECT COUNT(*) AS total FROM admins",
        fetchone=True
    )

    bot.send_message(
        message.chat.id,
        f"📊 آمار کلی ربات:\n\n"
        f"👥 کاربران دریافت‌کننده: {users['total']}\n"
        f"⬇️ کل دانلودها: {downloads['total']}\n"
        f"📂 فایل‌های فعال: {files['total']}\n"
        f"🛡 تعداد ادمین‌ها: {admins['total']}"
    )


def show_all_files(message):
    files = execute(
        """
        SELECT f.*, a.name
        FROM files f
        LEFT JOIN admins a ON a.user_id = f.admin_id
        WHERE f.deleted = 0
        ORDER BY f.id DESC
        """,
        fetchall=True
    )

    if not files:
        bot.send_message(message.chat.id, "هیچ فایلی وجود ندارد.")
        return

    text = "📂 فایل‌های ثبت‌شده:\n\n"

    for item in files:
        text += (
            f"📄 {item['file_name']}\n"
            f"👤 ادمین: {item['name'] or item['admin_id']}\n"
            f"⬇️ دانلود: {item['downloads']}\n"
            f"📅 تاریخ: {item['upload_date']}\n\n"
        )

    bot.send_message(message.chat.id, text)


# =========================
# پردازش حالت‌های مرحله‌ای
# =========================

def process_state(message, state):
    user_id = message.from_user.id
    action = state.get("action")
    text = message.text.strip()

    if action == "delete_after":
        try:
            seconds = int(text)

            if seconds < 1:
                raise ValueError

            execute(
                """
                INSERT INTO settings (admin_id, delete_after)
                VALUES (?, ?)
                ON CONFLICT(admin_id)
                DO UPDATE SET delete_after = EXCLUDED.delete_after
                """,
                (user_id, seconds),
                commit=True
            )

            clear_state(user_id)
            bot.send_message(
                message.chat.id,
                f"✅ مدت حذف خودکار روی {seconds} ثانیه تنظیم شد.",
                reply_markup=admin_keyboard()
            )

        except ValueError:
            bot.send_message(message.chat.id, "❌ فقط یک عدد مثبت ارسال کنید.")

    elif action == "add_admin":
        if not is_owner(user_id):
            clear_state(user_id)
            return

        try:
            target_id = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ آیدی باید عددی باشد.")
            return

        existing = get_admin(target_id)
        expire = datetime.now() + timedelta(days=DEFAULT_SUB_DAYS)

        if existing:
            execute(
                """
                UPDATE admins
                SET status = 'active', expire_at = ?
                WHERE user_id = ?
                """,
                (date_text(expire), target_id),
                commit=True
            )
        else:
            execute(
                """
                INSERT INTO admins
                (user_id, name, created_at, expire_at, status)
                VALUES (?, ?, ?, ?, 'active')
                """,
                (
                    target_id,
                    str(target_id),
                    now_text(),
                    date_text(expire)
                ),
                commit=True
            )

        execute(
            """
            INSERT OR IGNORE INTO settings (admin_id, delete_after)
            VALUES (?, ?)
            """,
            (target_id, DEFAULT_DELETE_AFTER),
            commit=True
        )

        clear_state(user_id)

        bot.send_message(
            message.chat.id,
            f"✅ ادمین {target_id} افزوده یا تمدید شد.",
            reply_markup=owner_keyboard()
        )

        safe_send(
            target_id,
            "✅ شما به عنوان ادمین ربات فعال شدید.\nبرای ورود از /panel استفاده کنید."
        )

    elif action == "remove_admin":
        if not is_owner(user_id):
            clear_state(user_id)
            return

        try:
            target_id = int(text)
        except ValueError:
            bot.send_message(message.chat.id, "❌ آیدی باید عددی باشد.")
            return

        execute(
            "UPDATE admins SET status = 'blocked' WHERE user_id = ?",
            (target_id,),
            commit=True
        )

        clear_state(user_id)

        bot.send_message(
            message.chat.id,
            f"✅ ادمین {target_id} مسدود شد.",
            reply_markup=owner_keyboard()
        )

        safe_send(target_id, "⛔ دسترسی ادمینی شما مسدود شد.")


# =========================
# Callbackهای فایل و کانال
# =========================

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_file:"))
def delete_file_callback(call):
    admin_id = call.from_user.id
    file_id = int(call.data.split(":")[1])

    file_row = execute(
        "SELECT * FROM files WHERE id = ?",
        (file_id,),
        fetchone=True
    )

    if not file_row or file_row["admin_id"] != admin_id:
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    execute(
        "UPDATE files SET deleted = 1 WHERE id = ?",
        (file_id,),
        commit=True
    )

    bot.answer_callback_query(call.id, "فایل حذف شد.")
    bot.edit_message_text(
        "🗑 فایل حذف شد و لینک آن غیرفعال گردید.",
        call.message.chat.id,
        call.message.message_id
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_caption:"))
def edit_caption_callback(call):
    admin_id = call.from_user.id
    file_id = int(call.data.split(":")[1])

    file_row = execute(
        "SELECT * FROM files WHERE id = ?",
        (file_id,),
        fetchone=True
    )

    if not file_row or file_row["admin_id"] != admin_id:
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    user_states[admin_id] = {
        "action": "edit_caption",
        "file_id": file_id
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        admin_id,
        "✏️ کپشن جدید را ارسال کنید.\n"
        "برای حذف کپشن، عبارت «بدون کپشن» را ارسال کنید."
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("file_stats:"))
def file_stats_callback(call):
    admin_id = call.from_user.id
    file_id = int(call.data.split(":")[1])

    file_row = execute(
        "SELECT * FROM files WHERE id = ?",
        (file_id,),
        fetchone=True
    )

    if not file_row or file_row["admin_id"] != admin_id:
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    users = execute(
        """
        SELECT username, user_id, timestamp
        FROM downloads
        WHERE file_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (file_id,),
        fetchall=True
    )

    text = (
        f"📊 آمار فایل:\n\n"
        f"📄 نام: {file_row['file_name']}\n"
        f"⬇️ تعداد دانلود: {file_row['downloads']}\n"
        f"📅 تاریخ آپلود: {file_row['upload_date']}\n\n"
        f"👥 آخرین دریافت‌کنندگان:\n"
    )

    if not users:
        text += "موردی ثبت نشده است."
    else:
        for user in users:
            text += (
                f"• {user['username'] or user['user_id']} - "
                f"{user['timestamp']}\n"
            )

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, text)


@bot.callback_query_handler(func=lambda call: call.data == "add_channel")
def add_channel_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    user_states[call.from_user.id] = {
        "action": "add_channel"
    }

    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "📢 اطلاعات کانال را در یک خط ارسال کنید:\n\n"
        "فرمت پیشنهادی:\n"
        "@channel_username | https://t.me/channel_username\n\n"
        "ربات باید در کانال ادمین باشد."
    )


@bot.callback_query_handler(func=lambda call: call.data == "clear_channels")
def clear_channels_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    execute(
        "DELETE FROM channels WHERE admin_id = ?",
        (call.from_user.id,),
        commit=True
    )

    bot.answer_callback_query(call.id, "کانال‌ها حذف شدند.")
    bot.send_message(call.message.chat.id, "✅ همه کانال‌های اجباری حذف شدند.")


# =========================
# تکمیل حالت‌های متنی
# =========================

_old_process_state = process_state


def process_state(message, state):
    user_id = message.from_user.id
    action = state.get("action")
    text = message.text.strip()

    if action == "edit_caption":
        caption = "" if text == "بدون کپشن" else text

        execute(
            "UPDATE files SET caption = ? WHERE id = ? AND admin_id = ?",
            (caption, state["file_id"], user_id),
            commit=True
        )

        clear_state(user_id)
        bot.send_message(
            message.chat.id,
            "✅ کپشن فایل ویرایش شد.",
            reply_markup=admin_keyboard()
        )
        return

    if action == "add_channel":
        parts = [part.strip() for part in text.split("|")]

        channel_username = parts[0]
        channel_link = parts[1] if len(parts) > 1 else ""

        if not channel_username:
            bot.send_message(message.chat.id, "❌ اطلاعات کانال ناقص است.")
            return

        channel_id = channel_username

        try:
            bot.get_chat(channel_id)
        except Exception:
            bot.send_message(
                message.chat.id,
                "❌ کانال پیدا نشد یا ربات در کانال دسترسی لازم ندارد."
            )
            return

        execute(
            """
            INSERT INTO channels
            (admin_id, channel_id, channel_username, channel_link)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                channel_id,
                channel_username,
                channel_link
            ),
            commit=True
        )

        clear_state(user_id)
        bot.send_message(
            message.chat.id,
            "✅ کانال اجباری با موفقیت ثبت شد.",
            reply_markup=admin_keyboard()
        )
        return

    _old_process_state(message, state)


# =========================
# بررسی دوره‌ای اشتراک‌ها
# =========================

def subscription_checker():
    while True:
        try:
            admins = execute(
                "SELECT * FROM admins WHERE status = 'active'",
                fetchall=True
            )

            current_time = datetime.now()

            for admin in admins:
                try:
                    expire_at = datetime.strptime(
                        admin["expire_at"],
                        "%Y-%m-%d %H:%M:%S"
                    )

                    if expire_at <= current_time:
                        execute(
                            """
                            UPDATE admins
                            SET status = 'expired'
                            WHERE user_id = ?
                            """,
                            (admin["user_id"],),
                            commit=True
                        )

                        safe_send(
                            admin["user_id"],
                            "⚠️ اشتراک شما منقضی شده است.\n"
                            "آپلود فایل و لینک‌های قبلی غیرفعال شدند."
                        )

                except Exception:
                    continue

        except Exception:
            pass

        time.sleep(60)


# =========================
# اجرای برنامه
# =========================


if __name__ == "__main__":
    # ساخت/آماده‌سازی دیتابیس
    init_database()

    # اجرای Flask در Thread جداگانه تا با Telegram polling تداخل نداشته باشد
    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True,
        name="flask-server"
    )
    flask_thread.start()

    # بررسی دوره‌ای اشتراک‌ها
    checker_thread = threading.Thread(
        target=subscription_checker,
        daemon=True,
        name="subscription-checker"
    )
    checker_thread.start()

    print("ربات با موفقیت اجرا شد.")
    print("Flask health server نیز در پس‌زمینه اجرا شد.")

    # Telegram webhook
    # Telegram sends every new update to the Flask endpoint above.
    # This lets a sleeping Render Free Web Service wake up on demand.
    setup_telegram_webhook()

    # Keep the main process alive while Flask handles webhook requests.
    while True:
        time.sleep(3600)
