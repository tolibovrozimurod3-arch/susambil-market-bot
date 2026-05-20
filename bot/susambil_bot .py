"""
╔══════════════════════════════════════════════╗
║         SUSAMBIL MARKET BOT 🌟               ║
║   O'zbekiston №1 Raqamli Mahsulotlar Bozori  ║
╚══════════════════════════════════════════════╝
"""

import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F
import asyncio

# ─── .env FAYLDAN O'QISH ────────────────────────────────────
load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_IDS  = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
CHANNEL_ID = os.getenv("CHANNEL_ID", "@susambil_market")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN topilmadi! .env faylni tekshiring.")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ─── MAHSULOT MA'LUMOTLAR BAZASI (keyinchalik SQLite/PostgreSQL) ──
PRODUCTS = {
    "bots": [
        {"id": "b1", "name": "🛒 Do'kon Bot", "desc": "Kichik biznes uchun to'liq savdo boti", "price": 150000, "emoji": "🛒"},
        {"id": "b2", "name": "📅 Navbat Bot", "desc": "Online navbat va bronlash boti", "price": 100000, "emoji": "📅"},
        {"id": "b3", "name": "📊 Quiz Bot", "desc": "Test va viktorina boti", "price": 80000, "emoji": "📊"},
        {"id": "b4", "name": "🍕 Restoran Bot", "desc": "Menu va buyurtma qabul boti", "price": 200000, "emoji": "🍕"},
    ],
    "templates": [
        {"id": "t1", "name": "📈 Biznes Reja", "desc": "Excel'da professional biznes reja", "price": 25000, "emoji": "📈"},
        {"id": "t2", "name": "💰 Budjet Nazorat", "desc": "Oilaviy/biznes budjet hisobi", "price": 15000, "emoji": "💰"},
        {"id": "t3", "name": "🎨 Canva Pack", "desc": "30ta SMM post shabloni", "price": 35000, "emoji": "🎨"},
        {"id": "t4", "name": "📋 Notion Workspace", "desc": "Ish boshqaruvi uchun Notion", "price": 20000, "emoji": "📋"},
    ],
    "courses": [
        {"id": "c1", "name": "🐍 Python Starter", "desc": "Boshlang'ichlar uchun Python PDF", "price": 30000, "emoji": "🐍"},
        {"id": "c2", "name": "📱 SMM Qo'llanma", "desc": "Ijtimoiy tarmoqlar boshqaruvi", "price": 40000, "emoji": "📱"},
        {"id": "c3", "name": "💼 CV Shablon", "desc": "5ta professional CV + cover letter", "price": 10000, "emoji": "💼"},
        {"id": "c4", "name": "🤖 AI Promptlar", "desc": "500+ tayyor AI prompt to'plami", "price": 20000, "emoji": "🤖"},
    ],
    "miniapps": [
        {"id": "m1", "name": "🧮 Hisob Kalkulator", "desc": "Biznes hisob-kitob mini app", "price": 50000, "emoji": "🧮"},
        {"id": "m2", "name": "📝 To-Do Manager", "desc": "Vazifalar boshqaruvi mini app", "price": 45000, "emoji": "📝"},
        {"id": "m3", "name": "🎯 Poll Creator", "desc": "So'rovnoma yaratish mini app", "price": 60000, "emoji": "🎯"},
    ],
}

# Foydalanuvchi savatchalari (xotirada, keyinchalik DB)
user_carts = {}

# ─── YORDAMCHI FUNKSIYALAR ───────────────────────────────────
def format_price(price: int) -> str:
    return f"{price:,} so'm".replace(",", " ")

def get_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🤖 Bot Bozor", callback_data="cat_bots"),
        InlineKeyboardButton(text="📦 Shablonlar", callback_data="cat_templates"),
    )
    builder.row(
        InlineKeyboardButton(text="📚 Bilim Bozori", callback_data="cat_courses"),
        InlineKeyboardButton(text="🛠 Mini App'lar", callback_data="cat_miniapps"),
    )
    builder.row(
        InlineKeyboardButton(text="🛒 Savatcha", callback_data="cart"),
        InlineKeyboardButton(text="📞 Aloqa", callback_data="contact"),
    )
    builder.row(
        InlineKeyboardButton(text="ℹ️ Susambil Market haqida", callback_data="about"),
    )
    return builder.as_markup()

def get_back_keyboard(back_to: str = "main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_{back_to}"))
    return builder.as_markup()

# ─── /START KOMANDASI ────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    welcome_text = f"""
🌟 <b>Susambil Market'ga xush kelibsiz!</b>

Salom, <b>{user.first_name}</b>! 👋

🏪 Bu yerda siz topa olasiz:
• 🤖 <b>Tayyor Telegram Botlar</b>
• 📦 <b>Biznes Shablonlar</b>
• 📚 <b>Raqamli Kurslar & PDF</b>
• 🛠 <b>Telegram Mini App'lar</b>

<i>O'zbekistonning №1 raqamli mahsulotlar bozori!</i>

👇 Quyidan tanlang:
    """
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

# ─── KATEGORIYALAR ───────────────────────────────────────────
CATEGORY_INFO = {
    "cat_bots":      ("🤖 BOT BOZOR", "bots", "Tayyor Telegram botlar — biznesingizni avtomatlashtiring!"),
    "cat_templates": ("📦 SHABLONLAR DO'KONI", "templates", "Excel, Notion, Canva — professional shablonlar!"),
    "cat_courses":   ("📚 BILIM BOZORI", "courses", "PDF kurslar, cheat sheet'lar — o'rganing va o'sing!"),
    "cat_miniapps":  ("🛠 MINI APP'LAR", "miniapps", "Tayyor Telegram Mini ilovalar!"),
}

@dp.callback_query(F.data.startswith("cat_"))
async def show_category(callback: types.CallbackQuery):
    cat_key = callback.data
    title, product_key, desc = CATEGORY_INFO[cat_key]
    products = PRODUCTS[product_key]

    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(
            InlineKeyboardButton(
                text=f"{p['emoji']} {p['name']} — {format_price(p['price'])}",
                callback_data=f"product_{product_key}_{p['id']}"
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="back_main"))

    text = f"<b>{title}</b>\n\n{desc}\n\n📋 <i>Mahsulotni tanlang:</i>"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

# ─── MAHSULOT TAFSILOTI ──────────────────────────────────────
@dp.callback_query(F.data.startswith("product_"))
async def show_product(callback: types.CallbackQuery):
    _, cat, prod_id = callback.data.split("_", 2)
    product = next((p for p in PRODUCTS[cat] if p["id"] == prod_id), None)
    if not product:
        await callback.answer("Mahsulot topilmadi!")
        return

    text = f"""
{product['emoji']} <b>{product['name']}</b>

📝 <b>Tavsif:</b>
{product['desc']}

💰 <b>Narxi:</b> {format_price(product['price'])}

⭐️ Sifat kafolatlangan!
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Savatga qo'shish", callback_data=f"addcart_{cat}_{prod_id}"),
        InlineKeyboardButton(text="💳 Hozir sotib olish", callback_data=f"buynow_{cat}_{prod_id}"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"cat_{cat}"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

# ─── SAVATCHA ────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("addcart_"))
async def add_to_cart(callback: types.CallbackQuery):
    _, cat, prod_id = callback.data.split("_", 2)
    user_id = callback.from_user.id
    product = next((p for p in PRODUCTS[cat] if p["id"] == prod_id), None)
    if not product:
        await callback.answer("Xatolik!")
        return

    if user_id not in user_carts:
        user_carts[user_id] = []

    # Takrorlanmasligi uchun tekshirish
    if any(item["id"] == prod_id for item in user_carts[user_id]):
        await callback.answer("✅ Bu mahsulot allaqachon savatda!")
        return

    user_carts[user_id].append({**product, "cat": cat})
    await callback.answer(f"✅ {product['name']} savatga qo'shildi!")

@dp.callback_query(F.data == "cart")
async def show_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cart = user_carts.get(user_id, [])

    if not cart:
        await callback.message.edit_text(
            "🛒 <b>Savatchangiz bo'sh</b>\n\nMahsulotlarni ko'rish uchun kategoriyalarni tanlang.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
        return

    total = sum(item["price"] for item in cart)
    items_text = "\n".join([f"• {item['emoji']} {item['name']} — {format_price(item['price'])}" for item in cart])

    text = f"""
🛒 <b>Sizning savatchingiz:</b>

{items_text}

──────────────────
💰 <b>Jami: {format_price(total)}</b>
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Buyurtma berish", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="🗑 Savatni tozalash", callback_data="clear_cart"))
    builder.row(InlineKeyboardButton(text="⬅️ Bosh menyu", callback_data="back_main"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery):
    user_carts[callback.from_user.id] = []
    await callback.answer("🗑 Savatcha tozalandi!")
    await show_cart(callback)

# ─── BUYURTMA ────────────────────────────────────────────────
@dp.callback_query(F.data == "checkout")
async def checkout(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cart = user_carts.get(user_id, [])
    if not cart:
        await callback.answer("Savatcha bo'sh!")
        return

    total = sum(item["price"] for item in cart)
    text = f"""
💳 <b>TO'LOV</b>

Jami summa: <b>{format_price(total)}</b>

📱 <b>To'lov usullari:</b>
• Payme: <code>9860 0000 0000 0000</code>
• Click: <code>9860 0000 0000 0000</code>

✅ To'lov qilganingizdan so'ng chekni shu yerga yuboring.
📦 Mahsulot 5 daqiqa ichida yuboriladi!

⚠️ <i>To'lov qilishdan oldin ma'lumotlarni tekshiring.</i>
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ To'lov qildim", callback_data="payment_sent"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cart"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "payment_sent")
async def payment_sent(callback: types.CallbackQuery):
    user = callback.from_user
    cart = user_carts.get(user.id, [])
    total = sum(item["price"] for item in cart)
    items = "\n".join([f"• {p['name']}" for p in cart])

    # Admin'ga xabar yuborish
    admin_text = f"""
🔔 <b>YANGI BUYURTMA!</b>

👤 Mijoz: <a href="tg://user?id={user.id}">{user.full_name}</a>
🆔 ID: <code>{user.id}</code>
📦 Mahsulotlar:
{items}
💰 Summa: {format_price(total)}
    """
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except:
            pass

    await callback.message.edit_text(
        "✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        "Adminimiz tez orada siz bilan bog'lanadi va mahsulotni yuboradi.\n\n"
        "⏱ Kutish vaqti: 5-15 daqiqa\n\n"
        "Rahmat! 🙏",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="back_main")
        ]])
    )
    user_carts[user.id] = []

# ─── HAQIDA ─────────────────────────────────────────────────
@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    text = """
🌟 <b>SUSAMBIL MARKET haqida</b>

O'zbekistonning №1 raqamli mahsulotlar bozori!

🎯 <b>Bizning maqsadimiz:</b>
Har bir tadbirkorga va dasturga arzon, sifatli raqamli yechimlar taqdim etish.

📊 <b>Raqamlarda:</b>
• 50+ tayyor mahsulot
• 500+ mamnun mijoz
• 5⭐️ o'rtacha reyting

🔒 <b>Kafolatlar:</b>
• 100% sifat kafolati
• 24 soat ichida yetkazib berish
• Texnik yordam

📢 Kanalimiz: @susambil_market
    """
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📢 Kanalga o'tish", url="https://t.me/susambil_market"))
    builder.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_main"))

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

# ─── ALOQA ───────────────────────────────────────────────────
@dp.callback_query(F.data == "contact")
async def contact(callback: types.CallbackQuery):
    text = """
📞 <b>Biz bilan bog'laning</b>

🤖 Admin: @susambil_admin
📢 Kanal: @susambil_market
📧 Email: info@susambilmarket.uz

⏰ Ish vaqti: 09:00 – 22:00

💬 Savol yoki takliflaringiz bo'lsa, bemalol yozing!
    """
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_keyboard())

# ─── ORQAGA ──────────────────────────────────────────────────
@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🌟 <b>Susambil Market</b>\n\n👇 Kategoriyani tanlang:",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data.startswith("back_"))
async def back_handler(callback: types.CallbackQuery):
    await back_main(callback)

# ─── ADMIN PANELI ────────────────────────────────────────────
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Ruxsat yo'q!")
        return

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="➕ Mahsulot qo'shish", callback_data="admin_add_product"))

    await message.answer(
        "👨‍💼 <b>ADMIN PANEL</b>\n\nXush kelibsiz, admin!",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return

    total_users = len(user_carts)
    total_products = sum(len(v) for v in PRODUCTS.values())

    text = f"""
📊 <b>STATISTIKA</b>

👥 Faol foydalanuvchilar: {total_users}
📦 Jami mahsulotlar: {total_products}
🛒 Ochiq savatlar: {sum(1 for c in user_carts.values() if c)}
    """
    await callback.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Admin panel", callback_data="back_admin")
        ]])
    )

# ─── BOTNI ISHGA TUSHIRISH ───────────────────────────────────
async def main():
    print("🚀 Susambil Market Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
