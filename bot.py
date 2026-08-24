import telebot
from http.server import BaseHTTPRequestHandler, HTTPServer
from telebot import types

TOKEN = "8915241769:AAHdKt2H-zUm8GavaWONoc-FfaTyGV_vhTo"
bot = telebot.TeleBot(TOKEN)

# زبان انتخابی هر کاربر
user_languages = {}


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
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
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
