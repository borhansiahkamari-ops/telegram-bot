# -*- coding: utf-8 -*-

import sqlite3
import threading
import secrets
import time
import os
from datetime import datetime, timedelta

import telebot
from telebot import types
from flask import Flask

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

BOT_TOKEN = "8915241769:AAGPPYUfe-Y882RiDAUqLGJhZ0JJFKsgIdk"

OWNER_ID = 6914909647

DEFAULT_DELETE_AFTER = 17

DEFAULT_SUB_DAYS = 30


# =========================
# راه‌اندازی ربات و دیتابیس
# =========================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DB_NAME = "file_sharing_bot.db"

db_lock = threading.RLock()

user_states = {}

pending_downloads = {}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def date_text(date_obj):
    return date_obj.strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    connection = sqlite3.connect(
        DB_NAME,
        check_same_thread=False,
        timeout=30
    )
    connection.row_factory = sqlite3.Row
    return connection


def execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    with db_lock:
        connection = get_db()
        try:
            cursor = connection.cursor()
            cursor.execute(query, params)

            if commit:
                connection.commit()

            if fetchone:
                return cursor.fetchone()

            if fetchall:
                return cursor.fetchall()

            return cursor.lastrowid

        finally:
            connection.close()


def init_database():
    with db_lock:
        connection = get_db()
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL,
                expire_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                channel_username TEXT,
                channel_link TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                admin_id INTEGER PRIMARY KEY,
                delete_after INTEGER NOT NULL DEFAULT 60
            )
        """)

        connection.commit()
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
                DO UPDATE SET delete_after = excluded.delete_after
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

    # Telegram polling
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=60,
                long_polling_timeout=60
            )
        except Exception as error:
            print("خطای polling:", error)
            time.sleep(5)
