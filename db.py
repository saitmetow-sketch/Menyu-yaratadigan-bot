import aiosqlite

DB_NAME = "database.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Foydalanuvchilar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                referred_by INTEGER,
                days_left INTEGER DEFAULT 3
            )
        """)

        # Kanallar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel TEXT PRIMARY KEY,
                channel_type TEXT,
                invite_link TEXT
            )
        """)

        # Adminlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                admin_id INTEGER PRIMARY KEY,
                added_by INTEGER
            )
        """)

        # So'rovli kanallar uchun arizalarni saqlash jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT,
                user_id INTEGER
            )
        """)

        # Foydalanuvchilarning ulangan botlari jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bots (
                creator_id INTEGER,
                bot_token TEXT PRIMARY KEY
            )
        """)

        await db.commit()


# --- FOYDALANUVCHILAR FUNKSIYALARI ---

async def add_user_if_new(user_id: int, username: str, referred_by: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute(
                    "INSERT INTO users (user_id, username, referred_by, days_left) VALUES (?, ?, ?, ?)",
                    (user_id, username, referred_by, 3)
                )
                await db.commit()


async def get_remaining_days(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT days_left FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 3


# --- KANALLAR FUNKSIYALARI ---

async def get_channels(channel_type: str) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT channel FROM channels WHERE channel_type = ?", (channel_type,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_channels_full(channel_type: str) -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT channel, invite_link FROM channels WHERE channel_type = ?", (channel_type,)) as cursor:
            return await cursor.fetchall()


async def add_channel(channel: str, channel_type: str, invite_link: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channels (channel, channel_type, invite_link) VALUES (?, ?, ?)",
            (channel, channel_type, invite_link)
        )
        await db.commit()


async def remove_channel(channel: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM channels WHERE channel = ?", (channel,))
        await db.commit()


# --- ADMINLAR FUNKSIYALARI ---

async def is_admin(user_id: int, owner_id: int) -> bool:
    if user_id == owner_id:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT admin_id FROM admins WHERE admin_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def add_admin(new_admin_id: int, added_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins (admin_id, added_by) VALUES (?, ?)",
            (new_admin_id, added_by)
        )
        await db.commit()


async def remove_admin(admin_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
        await db.commit()


async def get_admins() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT admin_id, added_by FROM admins") as cursor:
            return await cursor.fetchall()


# --- SO'ROVLI KANALLAR (JOIN REQUEST) FUNKSIYALARI ---

async def save_pending_request(chat_id: str, user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO pending_requests (chat_id, user_id) VALUES (?, ?)",
            (chat_id, user_id)
        )
        await db.commit()


async def get_pending_requests() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT chat_id, user_id FROM pending_requests") as cursor:
            return await cursor.fetchall()


async def clear_pending_requests():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM pending_requests")
        await db.commit()
