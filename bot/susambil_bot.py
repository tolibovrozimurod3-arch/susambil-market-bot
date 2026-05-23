"""
╔══════════════════════════════════════════════════════╗
║       SUSAMBIL MARKET BOT — Admin CMS + WebApp       ║
╚══════════════════════════════════════════════════════╝
"""

import logging, os, json, asyncio
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, WebAppInfo
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiohttp import web
import aiosqlite

load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_IDS  = list(map(int, os.getenv("ADMIN_IDS", "0").split(",")))
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://susambil-webapp.vercel.app")
DB_PATH    = os.getenv("DB_PATH", "susambil.db")
PORT       = int(os.getenv("PORT", 8080))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id          TEXT PRIMARY KEY,
                category    TEXT NOT NULL,
                name_uz     TEXT NOT NULL,
                name_en     TEXT DEFAULT '',
                name_ru     TEXT DEFAULT '',
                desc_uz     TEXT DEFAULT '',
                desc_en     TEXT DEFAULT '',
                desc_ru     TEXT DEFAULT '',
                url         TEXT DEFAULT '',
                img_url     TEXT DEFAULT '',
                file_type   TEXT DEFAULT '',
                file_size   TEXT DEFAULT '',
                color       TEXT DEFAULT '#6d28d9,#7c3aed',
                price       INTEGER DEFAULT 0,
                badge       TEXT DEFAULT '',
                rating      REAL DEFAULT 0.0,
                users       TEXT DEFAULT '0',
                action      TEXT DEFAULT 'open',
                active      INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS users (
                tg_id       INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                joined_at   TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()
    log.info("✅ DB tayyor")

async def save_item(item: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO items
            (id,category,name_uz,name_en,name_ru,desc_uz,desc_en,desc_ru,
             url,img_url,file_type,file_size,color,price,badge,rating,users,action)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            item.get('id'), item.get('category'),
            item.get('name_uz',''), item.get('name_en',''), item.get('name_ru',''),
            item.get('desc_uz',''), item.get('desc_en',''), item.get('desc_ru',''),
            item.get('url',''), item.get('img_url',''),
            item.get('file_type',''), item.get('file_size',''),
            item.get('color','#6d28d9,#7c3aed'),
            item.get('price', 0), item.get('badge',''),
            item.get('rating', 0.0), item.get('users','0'),
            item.get('action','open')
        ))
        await db.commit()

async def get_items(category=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if category:
            cur = await db.execute(
                "SELECT * FROM items WHERE category=? AND active=1 ORDER BY created_at DESC",
                (category,)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM items WHERE active=1 ORDER BY created_at DESC"
            )
        return [dict(r) for r in await cur.fetchall()]

async def delete_item(item_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE items SET active=0 WHERE id=?", (item_id,))
        await db.commit()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        cats = ['games','apps','images','files']
        result = {}
        for cat in cats:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM items WHERE category=? AND active=1", (cat,)
            )).fetchone()
            result[cat] = row[0] if row else 0
        total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        result['users'] = total_users
        return result

# ═══════════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════════

class AddItem(StatesGroup):
    category  = State()
    name_uz   = State()
    name_en   = State()
    name_ru   = State()
    desc_uz   = State()
    url       = State()
    img_url   = State()
    file_type = State()
    file_size = State()
    color     = State()
    price     = State()
    badge     = State()
    confirm   = State()

# ═══════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════

def kb_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Ilovani ochish", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton(text="🎮 O'yinlar", callback_data="tab_games"),
            InlineKeyboardButton(text="📱 Ilovalar", callback_data="tab_apps"),
        ],
        [
            InlineKeyboardButton(text="🖼 Rasmlar", callback_data="tab_images"),
            InlineKeyboardButton(text="📁 Fayllar", callback_data="tab_files"),
        ],
    ])

def kb_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi qo'shish", callback_data="admin_add")],
        [InlineKeyboardButton(text="📋 Ro'yxat ko'rish", callback_data="admin_list")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🌐 Ilovani ochish", web_app=WebAppInfo(url=WEBAPP_URL))],
    ])

def kb_categories():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎮 O'yin", callback_data="cat_games"),
            InlineKeyboardButton(text="📱 Ilova", callback_data="cat_apps"),
        ],
        [
            InlineKeyboardButton(text="🖼 Rasm", callback_data="cat_images"),
            InlineKeyboardButton(text="📁 Fayl", callback_data="cat_files"),
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel")],
    ])

def kb_skip_back():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="skip"),
            InlineKeyboardButton(text="❌ Bekor", callback_data="admin_cancel"),
        ]
    ])

def kb_badge():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔥 HOT",    callback_data="badge_hot"),
            InlineKeyboardButton(text="🆕 NEW",    callback_data="badge_new"),
        ],
        [
            InlineKeyboardButton(text="🆓 BEPUL",  callback_data="badge_free"),
            InlineKeyboardButton(text="➖ Yo'q",   callback_data="badge_none"),
        ],
    ])

def kb_colors():
    colors = [
        ("🟣 Binafsha", "#6d28d9,#7c3aed"),
        ("🔴 Qizil",    "#be185d,#db2777"),
        ("🔵 Ko'k",     "#0369a1,#0284c7"),
        ("🟢 Yashil",   "#059669,#10b981"),
        ("🟠 To'q sariq","#d97706,#f59e0b"),
        ("⚫ To'q",     "#1e1b4b,#312e81"),
    ]
    rows = []
    for i in range(0, len(colors), 2):
        row = []
        for name, val in colors[i:i+2]:
            row.append(InlineKeyboardButton(text=name, callback_data="color_"+val))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_confirm(item_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Saqlash",      callback_data=f"save_{item_id}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel")],
    ])

def kb_file_types():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 PDF",  callback_data="ftype_PDF"),
            InlineKeyboardButton(text="📊 XLSX", callback_data="ftype_XLSX"),
        ],
        [
            InlineKeyboardButton(text="📝 DOCX", callback_data="ftype_DOCX"),
            InlineKeyboardButton(text="📊 PPTX", callback_data="ftype_PPTX"),
        ],
        [
            InlineKeyboardButton(text="🗜 ZIP",  callback_data="ftype_ZIP"),
            InlineKeyboardButton(text="📦 Boshqa", callback_data="ftype_OTHER"),
        ],
    ])

def kb_list_items(items: list):
    rows = []
    for item in items[:20]:
        name = item.get('name_uz', item['id'])[:30]
        rows.append([InlineKeyboardButton(
            text=f"🗑 {name}",
            callback_data=f"del_{item['id']}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ═══════════════════════════════════════════
# /START
# ═══════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, username, full_name) VALUES (?,?,?)",
            (user.id, user.username or "", user.full_name)
        )
        await db.commit()

    text = (
        f"👋 Salom, <b>{user.first_name}</b>!\n\n"
        f"🌟 <b>Susambil Market</b> ga xush kelibsiz!\n\n"
        f"Quyidagi tugmani bosib ilovani oching:"
    )
    await message.answer(text, reply_markup=kb_main_menu())

# Tab buttons
@dp.callback_query(F.data.startswith("tab_"))
async def tab_handler(callback: types.CallbackQuery):
    tab = callback.data.replace("tab_", "")
    tab_names = {
        'games':  "🎮 O'yinlar",
        'apps':   "📱 Ilovalar",
        'images': "🖼 Rasmlar",
        'files':  "📁 Fayllar",
    }
    items = await get_items(tab)
    if not items:
        await callback.answer(f"{tab_names.get(tab,'')} bo'limi hozircha bo'sh", show_alert=True)
        return
    text = f"<b>{tab_names.get(tab, tab)}</b> — {len(items)} ta element\n\n"
    for item in items[:10]:
        price = "Bepul" if not item['price'] else f"{item['price']} coin"
        text += f"• <b>{item['name_uz']}</b> — {price}\n"
    await callback.message.edit_text(text, reply_markup=kb_main_menu())

# ═══════════════════════════════════════════
# /ADMIN
# ═══════════════════════════════════════════

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Ruxsat yo'q!")
        return
    stats = await get_stats()
    text = (
        f"👨‍💼 <b>ADMIN PANEL</b>\n\n"
        f"📊 Statistika:\n"
        f"• 🎮 O'yinlar: <b>{stats['games']}</b>\n"
        f"• 📱 Ilovalar: <b>{stats['apps']}</b>\n"
        f"• 🖼 Rasmlar: <b>{stats['images']}</b>\n"
        f"• 📁 Fayllar: <b>{stats['files']}</b>\n"
        f"• 👥 Foydalanuvchilar: <b>{stats['users']}</b>\n\n"
        f"Nima qilmoqchisiz?"
    )
    await message.answer(text, reply_markup=kb_admin_menu())

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    stats = await get_stats()
    text = (
        f"👨‍💼 <b>ADMIN PANEL</b>\n\n"
        f"🎮 {stats['games']} | 📱 {stats['apps']} | 🖼 {stats['images']} | 📁 {stats['files']}\n\n"
        f"Nima qilmoqchisiz?"
    )
    await callback.message.edit_text(text, reply_markup=kb_admin_menu())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    stats = await get_stats()
    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"🎮 O'yinlar: <b>{stats['games']}</b>\n"
        f"📱 Ilovalar: <b>{stats['apps']}</b>\n"
        f"🖼 Rasmlar: <b>{stats['images']}</b>\n"
        f"📁 Fayllar: <b>{stats['files']}</b>\n"
        f"👥 Foydalanuvchilar: <b>{stats['users']}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_back")]
        ])
    )

# ═══════════════════════════════════════════
# ADD FLOW
# ═══════════════════════════════════════════

@dp.callback_query(F.data == "admin_add")
async def admin_add_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AddItem.category)
    await callback.message.edit_text(
        "➕ <b>Yangi element qo'shish</b>\n\nQaysi bo'limga qo'shmoqchisiz?",
        reply_markup=kb_categories()
    )

@dp.callback_query(F.data.startswith("cat_"), StateFilter(AddItem.category))
async def add_category(callback: types.CallbackQuery, state: FSMContext):
    cat = callback.data.replace("cat_", "")
    cat_names = {'games': "O'yin", 'apps': "Ilova", 'images': "Rasm", 'files': "Fayl"}
    await state.update_data(
        category=cat,
        cat_name=cat_names.get(cat, cat),
        item_id=f"{cat}_{int(datetime.now().timestamp())}"
    )
    await state.set_state(AddItem.name_uz)
    await callback.message.edit_text(
        f"🇺🇿 <b>O'zbek tilida nomi</b>\n\n"
        f"Kategoriya: <b>{cat_names.get(cat,'')}</b>\n\n"
        f"Nomini yozing:"
    )

@dp.message(StateFilter(AddItem.name_uz))
async def add_name_uz(message: types.Message, state: FSMContext):
    await state.update_data(name_uz=message.text.strip())
    await state.set_state(AddItem.name_en)
    await message.answer(
        "🇬🇧 <b>Ingliz tilida nomi</b>\n\n"
        "Nomini yozing yoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.callback_query(F.data == "skip", StateFilter(AddItem.name_en))
async def skip_name_en(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(name_en=data.get('name_uz',''))
    await state.set_state(AddItem.name_ru)
    await callback.message.edit_text(
        "🇷🇺 <b>Rus tilida nomi</b>\n\nNomini yozing yoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.message(StateFilter(AddItem.name_en))
async def add_name_en(message: types.Message, state: FSMContext):
    await state.update_data(name_en=message.text.strip())
    await state.set_state(AddItem.name_ru)
    await message.answer(
        "🇷🇺 <b>Rus tilida nomi</b>\n\nNomini yozing yoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.callback_query(F.data == "skip", StateFilter(AddItem.name_ru))
async def skip_name_ru(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(name_ru=data.get('name_uz',''))
    await state.set_state(AddItem.desc_uz)
    await callback.message.edit_text(
        "📝 <b>Tavsifi</b> (ixtiyoriy)\n\nQisqacha tavsif yozing yoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.message(StateFilter(AddItem.name_ru))
async def add_name_ru(message: types.Message, state: FSMContext):
    await state.update_data(name_ru=message.text.strip())
    await state.set_state(AddItem.desc_uz)
    await message.answer(
        "📝 <b>Tavsifi</b> (ixtiyoriy)\n\nQisqacha tavsif yozing yoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.callback_query(F.data == "skip", StateFilter(AddItem.desc_uz))
async def skip_desc(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(desc_uz='', desc_en='', desc_ru='')
    await go_to_url(callback.message, state)

@dp.message(StateFilter(AddItem.desc_uz))
async def add_desc_uz(message: types.Message, state: FSMContext):
    await state.update_data(desc_uz=message.text.strip(), desc_en=message.text.strip(), desc_ru=message.text.strip())
    await go_to_url(message, state)

async def go_to_url(msg, state: FSMContext):
    data = await state.get_data()
    cat = data.get('category','')
    await state.set_state(AddItem.url)
    if cat == 'images':
        prompt = "🔗 <b>Rasm URL</b>\n\nRasmning to'g'ridan URL manzilini yuboring:"
    elif cat == 'files':
        prompt = "🔗 <b>Fayl URL</b>\n\nYuklab olish havolasini yuboring\n(Google Drive, Dropbox, Telegram va h.k.):"
    else:
        prompt = "🔗 <b>URL manzil</b>\n\nIlova yoki o'yin URL sini yuboring:"
    if hasattr(msg, 'edit_text'):
        await msg.edit_text(prompt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor", callback_data="admin_cancel")]
        ]))
    else:
        await msg.answer(prompt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor", callback_data="admin_cancel")]
        ]))

@dp.message(StateFilter(AddItem.url))
async def add_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    await state.update_data(url=url)
    data = await state.get_data()
    cat = data.get('category','')

    if cat == 'files':
        await state.set_state(AddItem.file_type)
        await message.answer(
            "📂 <b>Fayl turi</b>\n\nQaysi turdagi fayl?",
            reply_markup=kb_file_types()
        )
    elif cat == 'images':
        await state.update_data(img_url=url)
        await state.set_state(AddItem.price)
        await message.answer(
            "💰 <b>Narxi</b>\n\n0 = Bepul\nNarxni yozing (coin):",
            reply_markup=kb_skip_back()
        )
    else:
        await state.set_state(AddItem.img_url)
        await message.answer(
            "🖼 <b>Rasm URL</b> (ixtiyoriy)\n\n"
            "Thumbnail uchun rasm URL sini yuboring\n"
            "yoki o'tkazib yuboring:",
            reply_markup=kb_skip_back()
        )

@dp.callback_query(F.data.startswith("ftype_"), StateFilter(AddItem.file_type))
async def add_file_type(callback: types.CallbackQuery, state: FSMContext):
    ftype = callback.data.replace("ftype_", "")
    await state.update_data(file_type=ftype)
    await state.set_state(AddItem.file_size)
    await callback.message.edit_text(
        "📦 <b>Fayl hajmi</b>\n\nMasalan: 2.4 MB, 15 KB\nYoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.callback_query(F.data == "skip", StateFilter(AddItem.file_type))
async def skip_file_type(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(file_type='OTHER')
    await state.set_state(AddItem.file_size)
    await callback.message.edit_text(
        "📦 <b>Fayl hajmi</b>\n\nMasalan: 2.4 MB\nYoki o'tkazib yuboring:",
        reply_markup=kb_skip_back()
    )

@dp.message(StateFilter(AddItem.file_size))
async def add_file_size(message: types.Message, state: FSMContext):
    await state.update_data(file_size=message.text.strip())
    await state.set_state(AddItem.price)
    await message.answer("💰 <b>Narxi</b>\n\n0 = Bepul\nNarxni yozing:", reply_markup=kb_skip_back())

@dp.callback_query(F.data == "skip", StateFilter(AddItem.file_size))
async def skip_file_size(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(file_size='')
    await state.set_state(AddItem.price)
    await callback.message.edit_text("💰 <b>Narxi</b>\n\n0 = Bepul\nNarxni yozing:", reply_markup=kb_skip_back())

@dp.callback_query(F.data == "skip", StateFilter(AddItem.img_url))
async def skip_img(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(img_url='')
    await state.set_state(AddItem.color)
    await callback.message.edit_text(
        "🎨 <b>Thumbnail rangi</b>\n\nTugmachani tanlang:",
        reply_markup=kb_colors()
    )

@dp.message(StateFilter(AddItem.img_url))
async def add_img(message: types.Message, state: FSMContext):
    # Accept URL or photo
    if message.photo:
        photo = message.photo[-1]
        await state.update_data(img_url=f"tg://file/{photo.file_id}")
    else:
        await state.update_data(img_url=message.text.strip() if message.text else '')
    await state.set_state(AddItem.color)
    await message.answer(
        "🎨 <b>Thumbnail rangi</b>\n\nTugmachani tanlang:",
        reply_markup=kb_colors()
    )

@dp.callback_query(F.data.startswith("color_"), StateFilter(AddItem.color))
async def add_color(callback: types.CallbackQuery, state: FSMContext):
    color = callback.data.replace("color_", "")
    await state.update_data(color=color)
    await state.set_state(AddItem.price)
    await callback.message.edit_text(
        "💰 <b>Narxi</b>\n\n0 yuboring = Bepul\nNarxni yozing (coin):",
        reply_markup=kb_skip_back()
    )

@dp.callback_query(F.data == "skip", StateFilter(AddItem.color))
async def skip_color(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(color='#6d28d9,#7c3aed')
    await state.set_state(AddItem.price)
    await callback.message.edit_text(
        "💰 <b>Narxi</b>\n\n0 yuboring = Bepul\nNarxni yozing:",
        reply_markup=kb_skip_back()
    )

@dp.callback_query(F.data == "skip", StateFilter(AddItem.price))
async def skip_price(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(price=0)
    await state.set_state(AddItem.badge)
    await callback.message.edit_text(
        "🏷 <b>Badge (belgi)</b>\n\nQaysi belgini qo'shasiz?",
        reply_markup=kb_badge()
    )

@dp.message(StateFilter(AddItem.price))
async def add_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text.strip())
    except:
        price = 0
    await state.update_data(price=price)
    await state.set_state(AddItem.badge)
    await message.answer(
        "🏷 <b>Badge (belgi)</b>\n\nQaysi belgini qo'shasiz?",
        reply_markup=kb_badge()
    )

@dp.callback_query(F.data.startswith("badge_"), StateFilter(AddItem.badge))
async def add_badge(callback: types.CallbackQuery, state: FSMContext):
    badge = callback.data.replace("badge_", "")
    if badge == "none":
        badge = ""
    await state.update_data(badge=badge)
    await show_confirm(callback.message, state)

async def show_confirm(msg, state: FSMContext):
    data = await state.get_data()
    await state.set_state(AddItem.confirm)

    cat_icons = {'games':'🎮','apps':'📱','images':'🖼','files':'📁'}
    cat_names = {'games':"O'yin",'apps':"Ilova",'images':"Rasm",'files':"Fayl"}
    badge_labels = {'hot':'🔥 HOT','new':'🆕 NEW','free':'🆓 BEPUL','':'—'}

    text = (
        f"✅ <b>Tekshirib ko'ring</b>\n\n"
        f"{cat_icons.get(data.get('category',''),'📦')} Kategoriya: <b>{cat_names.get(data.get('category',''),'')}</b>\n\n"
        f"🇺🇿 Nomi: <b>{data.get('name_uz','')}</b>\n"
        f"🇬🇧 Nomi: <b>{data.get('name_en','')}</b>\n"
        f"🇷🇺 Nomi: <b>{data.get('name_ru','')}</b>\n\n"
        f"📝 Tavsif: {data.get('desc_uz','—')}\n"
        f"🔗 URL: <code>{data.get('url','—')}</code>\n"
        f"🖼 Rasm: {'✅' if data.get('img_url') else '—'}\n"
        f"💰 Narxi: <b>{'Bepul' if not data.get('price') else str(data.get('price'))+' coin'}</b>\n"
        f"🏷 Badge: <b>{badge_labels.get(data.get('badge',''),'—')}</b>\n"
    )
    if data.get('file_type'):
        text += f"📂 Fayl turi: <b>{data.get('file_type')}</b>\n"
    if data.get('file_size'):
        text += f"📦 Hajm: <b>{data.get('file_size')}</b>\n"

    await msg.edit_text(text, reply_markup=kb_confirm(data.get('item_id','')))

@dp.callback_query(F.data.startswith("save_"))
async def save_confirmed(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat = data.get('category','games')
    action_map = {'games':'play','apps':'open','images':'download','files':'download'}

    item = {
        'id':        data.get('item_id'),
        'category':  cat,
        'name_uz':   data.get('name_uz',''),
        'name_en':   data.get('name_en',''),
        'name_ru':   data.get('name_ru',''),
        'desc_uz':   data.get('desc_uz',''),
        'desc_en':   data.get('desc_en',''),
        'desc_ru':   data.get('desc_ru',''),
        'url':       data.get('url',''),
        'img_url':   data.get('img_url',''),
        'file_type': data.get('file_type',''),
        'file_size': data.get('file_size',''),
        'color':     data.get('color','#6d28d9,#7c3aed'),
        'price':     data.get('price',0),
        'badge':     data.get('badge',''),
        'rating':    0.0,
        'users':     '0',
        'action':    action_map.get(cat,'open'),
    }

    await save_item(item)
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>Muvaffaqiyatli saqlandi!</b>\n\n"
        f"<b>{item['name_uz']}</b> qo'shildi.\n"
        f"Ilova yangilanadi.\n\n"
        f"Yana qo'shmoqchimisiz?",
        reply_markup=kb_admin_menu()
    )

@dp.callback_query(F.data == "admin_cancel")
async def admin_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Bekor qilindi.",
        reply_markup=kb_admin_menu()
    )

# ═══════════════════════════════════════════
# LIST & DELETE
# ═══════════════════════════════════════════

@dp.callback_query(F.data == "admin_list")
async def admin_list(callback: types.CallbackQuery):
    items = await get_items()
    if not items:
        await callback.answer("Hali hech narsa qo'shilmagan", show_alert=True)
        return
    await callback.message.edit_text(
        f"📋 <b>Barcha elementlar</b> ({len(items)} ta)\n\n"
        f"O'chirish uchun bosing:",
        reply_markup=kb_list_items(items)
    )

@dp.callback_query(F.data.startswith("del_"))
async def delete_item_handler(callback: types.CallbackQuery):
    item_id = callback.data.replace("del_", "")
    await delete_item(item_id)
    items = await get_items()
    await callback.answer("✅ O'chirildi!")
    if items:
        await callback.message.edit_text(
            f"📋 <b>Elementlar</b> ({len(items)} ta)\n\nO'chirish uchun bosing:",
            reply_markup=kb_list_items(items)
        )
    else:
        await callback.message.edit_text("📋 Ro'yxat bo'sh", reply_markup=kb_admin_menu())

# ═══════════════════════════════════════════
# REST API (webapp uchun)
# ═══════════════════════════════════════════

async def api_items(request):
    """GET /api/items?category=games"""
    cat = request.rel_url.query.get('category', None)
    items = await get_items(cat)

    # Format for webapp
    def fmt(item):
        return {
            'id':       item['id'],
            'category': item['category'],
            'name':     {'uz': item['name_uz'], 'en': item['name_en'], 'ru': item['name_ru']},
            'desc':     {'uz': item['desc_uz'], 'en': item['desc_en'], 'ru': item['desc_ru']},
            'url':      item['url'],
            'img':      item['img_url'],
            'fileType': item['file_type'],
            'fileSize': item['file_size'],
            'color':    item['color'],
            'price':    item['price'],
            'badge':    item['badge'],
            'rating':   item['rating'],
            'users':    item['users'],
            'action':   item['action'],
        }

    data = [fmt(i) for i in items]
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type='application/json',
        headers={'Access-Control-Allow-Origin': '*'}
    )

async def api_health(request):
    return web.Response(text="OK", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/health',    api_health)
    app.router.add_get('/api/items', api_items)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    log.info(f"🌐 API server: http://0.0.0.0:{PORT}")

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

async def main():
    await init_db()
    await start_web_server()
    log.info("🚀 Susambil Market Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
