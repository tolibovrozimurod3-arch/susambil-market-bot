"""
Susambil Market — Ma'lumotlar Bazasi
SQLite (kichik miqyos) → PostgreSQL (katta miqyos)
"""

import aiosqlite
import asyncio
from datetime import datetime

DB_PATH = "susambil.db"

CREATE_TABLES = """
-- Foydalanuvchilar
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    tg_id       INTEGER UNIQUE NOT NULL,
    username    TEXT,
    full_name   TEXT,
    joined_at   TEXT DEFAULT (datetime('now')),
    is_banned   INTEGER DEFAULT 0
);

-- Kategoriyalar
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    emoji       TEXT,
    is_active   INTEGER DEFAULT 1
);

-- Mahsulotlar
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES categories(id),
    name        TEXT NOT NULL,
    description TEXT,
    price       INTEGER NOT NULL,
    file_id     TEXT,       -- Telegram file_id (PDF yoki rasm)
    emoji       TEXT,
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Buyurtmalar
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(tg_id),
    total_price INTEGER,
    status      TEXT DEFAULT 'pending',  -- pending, paid, delivered, cancelled
    created_at  TEXT DEFAULT (datetime('now')),
    paid_at     TEXT,
    delivered_at TEXT
);

-- Buyurtma tarkibi
CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER REFERENCES orders(id),
    product_id  INTEGER REFERENCES products(id),
    price       INTEGER NOT NULL
);

-- Savatcha
CREATE TABLE IF NOT EXISTS cart (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    product_id  INTEGER REFERENCES products(id),
    added_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, product_id)
);

-- Statistika
CREATE TABLE IF NOT EXISTS analytics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL,   -- 'view', 'add_cart', 'purchase'
    user_id     INTEGER,
    product_id  INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""

# Boshlang'ich kategoriyalar
SEED_CATEGORIES = [
    ("bots",      "🤖 Bot Bozor",      "🤖"),
    ("templates", "📦 Shablonlar",     "📦"),
    ("courses",   "📚 Bilim Bozori",   "📚"),
    ("miniapps",  "🛠 Mini App'lar",   "🛠"),
]

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        for slug, name, emoji in SEED_CATEGORIES:
            await db.execute(
                "INSERT OR IGNORE INTO categories (slug, name, emoji) VALUES (?, ?, ?)",
                (slug, name, emoji)
            )
        await db.commit()
    print("✅ Ma'lumotlar bazasi tayyor!")

# ─── DB OPERATSIYALARI ───────────────────────────────────────

async def get_or_create_user(tg_id, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, username, full_name) VALUES (?, ?, ?)",
            (tg_id, username, full_name)
        )
        await db.commit()

async def get_products_by_category(slug: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT p.id, p.name, p.description, p.price, p.emoji
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.slug = ? AND p.is_active = 1
        """, (slug,)) as cursor:
            return await cursor.fetchall()

async def create_order(user_id, items: list, total: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, total_price) VALUES (?, ?)",
            (user_id, total)
        )
        order_id = cursor.lastrowid
        for item in items:
            await db.execute(
                "INSERT INTO order_items (order_id, product_id, price) VALUES (?, ?, ?)",
                (order_id, item["id"], item["price"])
            )
        await db.commit()
        return order_id

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        users = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        orders = await (await db.execute("SELECT COUNT(*) FROM orders")).fetchone()
        revenue = await (await db.execute(
            "SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status='delivered'"
        )).fetchone()
        return {
            "users": users[0],
            "orders": orders[0],
            "revenue": revenue[0]
        }

if __name__ == "__main__":
    asyncio.run(init_db())
