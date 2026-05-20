"""
╔══════════════════════════════════════════════════════╗
║        SUSAMBIL MARKET — GAMING PLATFORM 🎮          ║
║   O'zbekistonning №1 O'yin va Mini App Platformasi   ║
╚══════════════════════════════════════════════════════╝
"""

import logging
import os
import json
import asyncio
from datetime import datetime, date
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, InlineQueryResultArticle, InputTextMessageContent
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web
import aiosqlite

load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_IDS   = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
CHANNEL     = os.getenv("CHANNEL_ID", "@susambilmarket")
WEBAPP_URL  = os.getenv("WEBAPP_URL", "https://susambil.vercel.app")
DB_PATH     = os.getenv("DB_PATH", "susambil.db")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp  = Dispatcher()

# ═══════════════════════════════════════════════════════
#  MA'LUMOTLAR BAZASI
# ═══════════════════════════════════════════════════════

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id       INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                coins       INTEGER DEFAULT 0,
                level       INTEGER DEFAULT 1,
                xp          INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                wins        INTEGER DEFAULT 0,
                streak      INTEGER DEFAULT 0,
                last_daily  TEXT DEFAULT '',
                joined_at   TEXT DEFAULT (datetime('now')),
                invited_by  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS scores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                game_id     TEXT,
                score       INTEGER,
                played_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS achievements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                badge       TEXT,
                earned_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                task        TEXT,
                done        INTEGER DEFAULT 0,
                task_date   TEXT
            );
        """)
        await db.commit()

async def get_user(tg_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)) as cur:
            return await cur.fetchone()

async def create_user(tg_id, username, full_name, invited_by=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id,username,full_name,invited_by) VALUES (?,?,?,?)",
            (tg_id, username, full_name, invited_by)
        )
        await db.commit()

async def add_coins(tg_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET coins=coins+? WHERE tg_id=?", (amount, tg_id))
        await db.commit()

async def add_xp(tg_id, xp):
    async with aiosqlite.connect(DB_PATH) as db:
        user = await get_user(tg_id)
        if not user: return
        new_xp = user['xp'] + xp
        new_level = 1 + new_xp // 500  # har 500 XP = 1 level
        await db.execute(
            "UPDATE users SET xp=?, level=? WHERE tg_id=?",
            (new_xp, new_level, tg_id)
        )
        await db.commit()
        return new_level > user['level']  # level oshganini qaytaradi

async def save_score(user_id, game_id, score):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO scores (user_id,game_id,score) VALUES (?,?,?)",
            (user_id, game_id, score)
        )
        await db.execute("UPDATE users SET games_played=games_played+1 WHERE tg_id=?", (user_id,))
        await db.commit()

async def get_leaderboard(game_id=None, limit=10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if game_id:
            query = """
                SELECT u.full_name, u.username, MAX(s.score) as best, u.level
                FROM scores s JOIN users u ON s.user_id=u.tg_id
                WHERE s.game_id=?
                GROUP BY s.user_id ORDER BY best DESC LIMIT ?
            """
            async with db.execute(query, (game_id, limit)) as cur:
                return await cur.fetchall()
        else:
            query = """
                SELECT full_name, username, coins, level, xp, games_played
                FROM users ORDER BY coins DESC LIMIT ?
            """
            async with db.execute(query, (limit,)) as cur:
                return await cur.fetchall()

async def claim_daily(tg_id):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        user = await get_user(tg_id)
        if user and user['last_daily'] == today:
            return False, 0
        streak = (user['streak'] + 1) if user else 1
        coins = 50 + (streak * 10)  # streak bonus
        await db.execute(
            "UPDATE users SET coins=coins+?, last_daily=?, streak=? WHERE tg_id=?",
            (coins, today, streak, tg_id)
        )
        await db.commit()
        return True, coins

# ═══════════════════════════════════════════════════════
#  O'YIN KATALOGI
# ═══════════════════════════════════════════════════════

GAMES = {
    "sozlik": {
        "name": "🔤 So'zlik",
        "desc": "5 harfli o'zbek so'zini top! Wordle o'zbek tilida.",
        "genre": "🧠 Mantiq",
        "players": "12.5K",
        "rating": "4.9",
        "coins": 20,
        "emoji": "🔤",
    },
    "calculator": {
        "name": "🧮 Biznes Kalkulator",
        "desc": "Foyda, ROI va narx hisoblash mini ilovasi.",
        "genre": "🛠 Asbob",
        "players": "8.2K",
        "rating": "4.8",
        "coins": 0,
        "emoji": "🧮",
    },
    "quiz_uz": {
        "name": "❓ Bilim Bellashuvi",
        "desc": "O'zbekiston tarixi, geografiya, fan bo'yicha test.",
        "genre": "🎓 Bilim",
        "players": "5.1K",
        "rating": "4.7",
        "coins": 30,
        "emoji": "❓",
    },
    "math_duel": {
        "name": "🔢 Tez Hisob",
        "desc": "30 soniyada imkon qadar ko'p misol yesh!",
        "genre": "⚡ Tezkor",
        "players": "9.8K",
        "rating": "4.8",
        "coins": 25,
        "emoji": "🔢",
    },
    "memory": {
        "name": "🃏 Xotira O'yini",
        "desc": "Kartochkalarni juftlab top — xotirangni sinab ko'r!",
        "genre": "🧩 Puzzle",
        "players": "7.3K",
        "rating": "4.6",
        "coins": 15,
        "emoji": "🃏",
    },
    "currency": {
        "name": "💱 Valyuta",
        "desc": "Real vaqt valyuta kurslari konvertori.",
        "genre": "🛠 Asbob",
        "players": "4.5K",
        "rating": "4.7",
        "coins": 0,
        "emoji": "💱",
    },
}

GENRES = {
    "🧠 Mantiq": ["sozlik"],
    "⚡ Tezkor": ["math_duel"],
    "🎓 Bilim":  ["quiz_uz"],
    "🧩 Puzzle": ["memory"],
    "🛠 Asbob":  ["calculator", "currency"],
}

LEVEL_NAMES = {
    1: "🌱 Yangi boshlovchi",
    2: "⭐ O'rganuvchi",
    3: "🌟 Faol o'yinchi",
    4: "💫 Tajribali",
    5: "🔥 Ustoz",
    6: "💎 Mestr",
    7: "👑 Chempion",
    8: "🏆 Legend",
    9: "🌈 Superstar",
    10: "🚀 Susambil Pro",
}

def level_name(level):
    return LEVEL_NAMES.get(min(level, 10), "🚀 Susambil Pro")

def xp_bar(xp):
    filled = (xp % 500) // 50
    bar = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {xp%500}/500 XP"

# ═══════════════════════════════════════════════════════
#  KLAVIATURALAR
# ═══════════════════════════════════════════════════════

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 O'yinlar", callback_data="games_home"),
            InlineKeyboardButton(text="🛠 Mini App'lar", callback_data="miniapps"),
        ],
        [
            InlineKeyboardButton(text="👤 Profilim", callback_data="profile"),
            InlineKeyboardButton(text="🏆 Reyting", callback_data="leaderboard"),
        ],
        [
            InlineKeyboardButton(text="🎁 Kunlik sovg'a", callback_data="daily"),
            InlineKeyboardButton(text="👥 Do'stlarni taklif", callback_data="invite"),
        ],
        [
            InlineKeyboardButton(text="🛒 Market", callback_data="market"),
            InlineKeyboardButton(text="📢 Kanal", url=f"https://t.me/susambilmarket"),
        ],
    ])

# ═══════════════════════════════════════════════════════
#  HANDLERLAR
# ═══════════════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    args = message.text.split()
    invited_by = int(args[1].replace("ref_","")) if len(args)>1 and args[1].startswith("ref_") else 0

    await create_user(user.id, user.username or "", user.full_name, invited_by)

    if invited_by and invited_by != user.id:
        await add_coins(invited_by, 100)
        try:
            await bot.send_message(invited_by,
                f"🎉 Do'stingiz <b>{user.full_name}</b> qo'shildi!\n+100 🪙 coin oldiniz!")
        except: pass

    db_user = await get_user(user.id)
    coins = db_user['coins'] if db_user else 0

    text = f"""
🌟 <b>SUSAMBIL MARKET</b> ga xush kelibsiz!

Salom, <b>{user.first_name}</b>! 👋
💰 Balansingiz: <b>{coins} 🪙</b>

🎮 O'yin o'ynang → coin yig'ing
🏆 Reytingda yuqoriga chiqing
🎁 Har kuni sovg'a oling
👥 Do'stlarni taklif qiling → bonus oling

<i>O'zbekistonning №1 o'yin platformasi!</i>
"""
    await message.answer(text, reply_markup=main_menu())

# ── O'YINLAR BOSH SAHIFASI ───────────────────────────────────
@dp.callback_query(F.data == "games_home")
async def games_home(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    for gid, g in GAMES.items():
        coin_text = f" • +{g['coins']}🪙" if g['coins'] > 0 else ""
        builder.row(InlineKeyboardButton(
            text=f"{g['emoji']} {g['name']} ⭐{g['rating']}{coin_text}",
            callback_data=f"game_{gid}"
        ))
    builder.row(
        InlineKeyboardButton(text="🏆 Top o'yinchilar", callback_data="leaderboard"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"),
    )

    text = "🎮 <b>O'YINLAR KATALOGI</b>\n\nO'yin tanlang va coin yig'ing! 🪙"
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── O'YIN TAFSILOTI ──────────────────────────────────────────
@dp.callback_query(F.data.startswith("game_"))
async def game_detail(callback: types.CallbackQuery):
    gid = callback.data.replace("game_", "")
    g = GAMES.get(gid)
    if not g:
        await callback.answer("O'yin topilmadi!")
        return

    # Leaderboard top 3
    top = await get_leaderboard(gid, 3)
    medals = ["🥇","🥈","🥉"]
    lb_text = ""
    if top:
        lb_text = "\n\n🏆 <b>Top o'yinchilar:</b>\n"
        for i, row in enumerate(top):
            name = row['full_name'] or row['username'] or "Noma'lum"
            lb_text += f"{medals[i]} {name} — {row['best']} ball\n"

    text = f"""
{g['emoji']} <b>{g['name']}</b>

📝 {g['desc']}
🎯 Janr: {g['genre']}
👥 O'ynaganlar: {g['players']}
⭐ Reyting: {g['rating']}/5.0
💰 Mukofot: +{g['coins']} 🪙 har o'yinda
{lb_text}"""

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"🚀 O'ynash",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/games/{gid}")
    ))
    builder.row(
        InlineKeyboardButton(text="🏆 Reyting", callback_data=f"lb_{gid}"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="games_home"),
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── MINI APP'LAR ─────────────────────────────────────────────
@dp.callback_query(F.data == "miniapps")
async def miniapps(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="🧮 Biznes Kalkulator",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/apps/calculator")
    ))
    builder.row(InlineKeyboardButton(
        text="💱 Valyuta Konvertor",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/apps/currency")
    ))
    builder.row(InlineKeyboardButton(
        text="📊 CV Yaratuvchi",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/apps/cv")
    ))
    builder.row(InlineKeyboardButton(
        text="📅 Jadval Tuzuvchi",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/apps/schedule")
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"))

    await callback.message.edit_text(
        "🛠 <b>MINI APP'LAR</b>\n\nQulay asboblar — to'g'ridan Telegramda!",
        reply_markup=builder.as_markup()
    )

# ── PROFIL ───────────────────────────────────────────────────
@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Profil topilmadi!")
        return

    lvl = user['level']
    text = f"""
👤 <b>PROFIL</b>

🏷 Ism: <b>{user['full_name']}</b>
🎖 Daraja: <b>{level_name(lvl)} (Level {lvl})</b>
📊 Tajriba: {xp_bar(user['xp'])}

💰 Coinlar: <b>{user['coins']} 🪙</b>
🎮 O'yinlar: <b>{user['games_played']}</b>
🏆 G'alabalar: <b>{user['wins']}</b>
🔥 Seriya: <b>{user['streak']} kun</b>

🔗 Referal: <code>https://t.me/susambilmarketbot?start=ref_{user['tg_id']}</code>
"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏅 Yutuqlarim", callback_data="achievements"),
        InlineKeyboardButton(text="📊 Statistika", callback_data="stats"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── LEADERBOARD ──────────────────────────────────────────────
@dp.callback_query(F.data == "leaderboard")
async def leaderboard(callback: types.CallbackQuery):
    top = await get_leaderboard(limit=10)
    medals = ["🥇","🥈","🥉"] + ["4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    text = "🏆 <b>GLOBAL REYTING</b>\n\n"

    if top:
        for i, row in enumerate(top):
            name = row['full_name'] or row['username'] or "Noma'lum"
            text += f"{medals[i]} <b>{name}</b> — {row['coins']}🪙 · Lv.{row['level']}\n"
    else:
        text += "Hali o'yinchilar yo'q. Birinchi bo'ling! 🚀"

    builder = InlineKeyboardBuilder()
    for gid, g in list(GAMES.items())[:4]:
        builder.row(InlineKeyboardButton(
            text=f"{g['emoji']} {g['name']} reytingi",
            callback_data=f"lb_{gid}"
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("lb_"))
async def game_leaderboard(callback: types.CallbackQuery):
    gid = callback.data.replace("lb_", "")
    g = GAMES.get(gid, {})
    top = await get_leaderboard(gid, 10)
    medals = ["🥇","🥈","🥉"] + ["4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    text = f"🏆 <b>{g.get('name','O\'yin')} — TOP 10</b>\n\n"
    if top:
        for i, row in enumerate(top):
            name = row['full_name'] or row['username'] or "Noma'lum"
            text += f"{medals[i]} <b>{name}</b> — {row['best']} ball\n"
    else:
        text += "Hali hech kim o'ynamagan. Birinchi bo'ling! 🚀"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"🚀 O'ynash", callback_data=f"game_{gid}"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="leaderboard"),
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── KUNLIK SOVG'A ────────────────────────────────────────────
@dp.callback_query(F.data == "daily")
async def daily_reward(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    claimed, coins = await claim_daily(user_id)

    if claimed:
        user = await get_user(user_id)
        await add_xp(user_id, 50)
        text = f"""
🎁 <b>KUNLIK SOVG'A!</b>

✅ Bugungi sovg'angiz olindi!

💰 +{coins} 🪙 coin
⭐ +50 XP
🔥 Seriya: {user['streak'] if user else 1} kun

<i>Ertaga yana keling — yangi sovg'a kutmoqda!</i>
"""
    else:
        text = "⏰ <b>Bugungi sovg'ani allaqachon oldingiz!</b>\n\nErtaga yana keling! 🎁"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎮 O'ynash", callback_data="games_home"),
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"),
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── DO'STLARNI TAKLIF ────────────────────────────────────────
@dp.callback_query(F.data == "invite")
async def invite(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    link = f"https://t.me/susambilmarketbot?start=ref_{user_id}"
    text = f"""
👥 <b>DO'STLARNI TAKLIF QIL</b>

Har bir taklif qilgan do'stingiz uchun:
🪙 +100 coin olasiz
🌟 Do'stingiz ham +50 coin oladi

📎 Sizning havola:
<code>{link}</code>

Ulashing va birga o'ynang! 🎮
"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📤 Ulashish",
        url=f"https://t.me/share/url?url={link}&text=Susambil%20Market'da%20birga%20o'ynaylik!"
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── MARKET ───────────────────────────────────────────────────
@dp.callback_query(F.data == "market")
async def market(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🤖 Bot Bozor", callback_data="cat_bots"))
    builder.row(InlineKeyboardButton(text="📦 Shablonlar", callback_data="cat_templates"))
    builder.row(InlineKeyboardButton(text="📚 Bilim Bozori", callback_data="cat_courses"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"))
    await callback.message.edit_text(
        "🛒 <b>SUSAMBIL MARKET</b>\n\nRaqamli mahsulotlar do'koni!",
        reply_markup=builder.as_markup()
    )

# ── SCORE QABUL QILISH (WebApp'dan) ─────────────────────────
@dp.message(F.web_app_data)
async def web_app_data(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
        game_id = data.get("game_id")
        score   = int(data.get("score", 0))
        user_id = message.from_user.id

        g = GAMES.get(game_id, {})
        coins_earned = g.get("coins", 10)

        await save_score(user_id, game_id, score)
        await add_coins(user_id, coins_earned)
        leveled = await add_xp(user_id, score // 10 + 20)

        user = await get_user(user_id)
        level_up_text = f"\n\n🎊 <b>LEVEL UP!</b> Siz {level_name(user['level'])} bo'ldingiz!" if leveled else ""

        text = f"""
🎮 <b>O'YIN YAKUNLANDI!</b>

🎯 O'yin: {g.get('name', game_id)}
📊 Natija: <b>{score} ball</b>
💰 Mukofot: +{coins_earned} 🪙
💼 Jami coin: {user['coins'] if user else '?'} 🪙
{level_up_text}
"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔄 Qayta", callback_data=f"game_{game_id}"),
            InlineKeyboardButton(text="🏆 Reyting", callback_data=f"lb_{game_id}"),
        )
        builder.row(InlineKeyboardButton(text="🏠 Bosh menu", callback_data="back_main"))
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        await message.answer(f"Xatolik: {e}")

# ── YUTUQLAR ─────────────────────────────────────────────────
@dp.callback_query(F.data == "achievements")
async def achievements(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Profil topilmadi!")
        return

    badges = []
    if user['games_played'] >= 1:   badges.append("🎮 Birinchi o'yin")
    if user['games_played'] >= 10:  badges.append("🔟 10 ta o'yin")
    if user['games_played'] >= 50:  badges.append("🏅 50 ta o'yin")
    if user['coins'] >= 100:        badges.append("💰 100 coin")
    if user['coins'] >= 1000:       badges.append("💎 1000 coin")
    if user['streak'] >= 3:         badges.append("🔥 3 kunlik seriya")
    if user['streak'] >= 7:         badges.append("⚡ Haftalik seriya")
    if user['level'] >= 3:          badges.append("⭐ 3-daraja")
    if user['level'] >= 5:          badges.append("🌟 5-daraja")

    text = "🏅 <b>YUTUQLARIM</b>\n\n"
    text += "\n".join([f"✅ {b}" for b in badges]) if badges else "Hali yutuq yo'q. O'ynang va yig'ing! 🎮"
    text += f"\n\n<i>Jami: {len(badges)} ta yutuq</i>"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Profil", callback_data="profile"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# ── ORQAGA ────────────────────────────────────────────────────
@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    user = await get_user(callback.from_user.id)
    coins = user['coins'] if user else 0
    name  = callback.from_user.first_name
    text = f"""
🌟 <b>SUSAMBIL MARKET</b>

👋 {name} | 💰 {coins} 🪙

🎮 O'ynang, yig'ing, yuting!
"""
    await callback.message.edit_text(text, reply_markup=main_menu())

# ── ADMIN ─────────────────────────────────────────────────────
@dp.message(Command("admin"))
async def admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        users  = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        scores = await (await db.execute("SELECT COUNT(*) FROM scores")).fetchone()
        coins  = await (await db.execute("SELECT SUM(coins) FROM users")).fetchone()

    text = f"""
👨‍💼 <b>ADMIN PANEL</b>

👥 Foydalanuvchilar: {users[0]}
🎮 O'yinlar o'ynalgan: {scores[0]}
💰 Jami coinlar: {coins[0] or 0}
"""
    await message.answer(text)

# ═══════════════════════════════════════════════════════
#  HEALTH CHECK + ISHGA TUSHIRISH
# ═══════════════════════════════════════════════════════

async def health_check(request):
    return web.Response(text="✅ Susambil Market ishlayapti!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Health check: http://0.0.0.0:{port}")

async def main():
    await init_db()
    await start_web_server()
    print("🚀 Susambil Market Gaming Platform ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
