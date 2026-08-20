import telebot
import re
import time
import logging

# ==========================
# CONFIG
# ==========================

TOKEN = "8991333895:AAFuSkby-1uccGcGeOhpuk088URI4GIqoZo"
ADMIN_ID = 6914909647

MUTE_DURATION = 60
MAX_WARNINGS = 3

WELCOME_MSG = "🎉 Welcome {name}! Glad to have you here."
BYE_MSG = "👋 Goodbye {name}! Hope to see you again."

# ==========================
# LOGGING
# ==========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================
# BOT
# ==========================

bot = telebot.TeleBot(TOKEN)

warnings = {}

BAD_WORDS = [
    "ass", "asshole", "bastard", "bitch", "bollocks", "bullshit",
    "crap", "damn", "dick", "douche", "fuck", "fucker", "fucking",
    "hell", "jackass", "piss", "pussy", "screw", "shit", "slut",
    "twat", "wanker", "whore",
    "motherfucker", "cunt", "cock",
    "fag", "faggot", "retard",

    "b!tch", "b1tch",
    "f*ck", "f**k", "f4ck",
    "sh!t", "s#it",
    "d!ck", "d1ck",
    "a$$",
    "fuk", "fck", "phuck", "fuq",

    "free bitcoins",
    "click here",
    "earn money fast",
    "get rich"
]
PROFANITY_PATTERNS = [
    r"f[!1i*\-_.\s]*u[!1i*\-_.\s]*c[!1i*\-_.\s]*k",
    r"b[!1i*\-_.\s]*i[!1i*\-_.\s]*t[!1i*\-_.\s]*c[!1i*\-_.\s]*h",
    r"s[!1i*\-_.\s]*h[!1i*\-_.\s]*i[!1i*\-_.\s]*t",
    r"a[!1i*\-_.\s]*s[!1i*\-_.\s]*s",
    r"d[!1i*\-_.\s]*i[!1i*\-_.\s]*c[!1i*\-_.\s]*k",
    r"c[!1i*\-_.\s]*u[!1i*\-_.\s]*n[!1i*\-_.\s]*t",
    r"c[!1i*\-_.\s]*o[!1i*\-_.\s]*c[!1i*\-_.\s]*k",
    r"p[!1i*\-_.\s]*u[!1i*\-_.\s]*s[!1i*\-_.\s]*s[!1i*\-_.\s]*y",
    r"w[!1i*\-_.\s]*h[!1i*\-_.\s]*o[!1i*\-_.\s]*r[!1i*\-_.\s]*e",
    r"f[!1i*\-_.\s]*a[!1i*\-_.\s]*g[!1i*\-_.\s]*g[!1i*\-_.\s]*o[!1i*\-_.\s]*t",
    r"r[!1i*\-_.\s]*e[!1i*\-_.\s]*t[!1i*\-_.\s]*a[!1i*\-_.\s]*r[!1i*\-_.\s]*d"
]

# ==========================
# HELPERS
# ==========================
def is_profanity(text):

    if not text:
        return False

    clean = text.lower().replace(" ", "")

    for pattern in PROFANITY_PATTERNS:
        if re.search(pattern, clean):
            return True

    for word in BAD_WORDS:
        if word.lower() in clean:
            return True

    return False

def is_spam(text):

    if not text:
        return False

    spam_patterns = [
        r'https?://',
        r'www\.',
        r't\.me/',
        r'@',
        r'free\s+bitcoins',
        r'click\s+here',
        r'earn\s+money',
        r'get\s+rich'
    ]

    for pattern in spam_patterns:
        if re.search(pattern, text.lower()):
            return True

    return False

# ==========================
# START
# ==========================

@bot.message_handler(commands=["start"])
def start(message):

    bot.reply_to(
        message,
        "🤖 AdminGuard Bot Online"
    )

# ==========================
# ADMIN
# ==========================

@bot.message_handler(commands=["admin"])
def admin(message):

    if message.from_user.id != ADMIN_ID:
        return

    bot.reply_to(
        message,
        "👑 Admin Panel Active"
    )

# ==========================
# WORDS
# ==========================

@bot.message_handler(commands=["words"])
def words(message):

    if message.from_user.id != ADMIN_ID:
        return

    bot.reply_to(
        message,
        "\n".join(BAD_WORDS)
    )

# ==========================
# ADD WORD
# ==========================

@bot.message_handler(commands=["addword"])
def add_word(message):

    if message.from_user.id != ADMIN_ID:
        return

    word = message.text.replace("/addword", "").strip().lower()

    if not word:
        return

    BAD_WORDS.append(word)

    bot.reply_to(
        message,
        f"✅ Added: {word}"
    )

# ==========================
# DELETE WORD
# ==========================

@bot.message_handler(commands=["delword"])
def del_word(message):

    if message.from_user.id != ADMIN_ID:
        return

    word = message.text.replace("/delword", "").strip().lower()

    if word in BAD_WORDS:
        BAD_WORDS.remove(word)

    bot.reply_to(
        message,
        f"✅ Removed: {word}"
    )

# ==========================
# NEW MEMBER
# ==========================

@bot.message_handler(content_types=["new_chat_members"])
def welcome(message):

    for member in message.new_chat_members:

        bot.send_message(
            message.chat.id,
            WELCOME_MSG.format(
                name=user_name(member)
            )
        )

# ==========================
# LEFT MEMBER
# ==========================

@bot.message_handler(content_types=["left_chat_member"])
def goodbye(message):

    bot.send_message(
        message.chat.id,
        BYE_MSG.format(
            name=user_name(
                message.left_chat_member
            )
        )
    )

# ==========================
# FILTER
# ==========================

@bot.message_handler(func=lambda m: True, content_types=["text"])
def filter_message(message):

    if message.from_user.id == ADMIN_ID:
        return

    user_id = message.from_user.id

    if is_profanity(message.text):

        try:
            bot.delete_message(
                message.chat.id,
                message.message_id
            )
        except Exception as e:
            print(e)

        warnings[user_id] = warnings.get(user_id, 0) + 1

        bot.send_message(
            message.chat.id,
            f"⚠️ Warning {warnings[user_id]}/{MAX_WARNINGS}"
        )

        if warnings[user_id] >= MAX_WARNINGS:

            try:
                bot.restrict_chat_member(
                    message.chat.id,
                    user_id,
                    until_date=int(time.time()) + MUTE_DURATION
                )

                bot.send_message(
                    message.chat.id,
                    "🔇 User muted."
                )

            except Exception as e:
                print(e)

            warnings[user_id] = 0

        return

    if is_spam(message.text):

        try:
            bot.delete_message(
                message.chat.id,
                message.message_id
            )

            bot.send_message(
                message.chat.id,
                "🚫 Links are not allowed."
            )

        except Exception as e:
            print(e)

# ==========================
# RUN
# ==========================

print("Bot Started...")

bot.infinity_polling(skip_pending=True)
