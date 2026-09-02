import aiosqlite
from datetime import datetime, timedelta

DB_NAME = "database.db"


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                joined_at TEXT,
                expire_at TEXT,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                type TEXT,
                invite_link TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER
            )
        """)
        await db.commit()


async def add_user_if_new(user_id: int, username: str, referred_by: int = None) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            joined_at = datetime.now().isoformat()
            expire_at = (datetime.now() + timedelta(days=3)).isoformat()
            await db.execute(
                "INSERT INTO users (user_id, username, joined_at, expire_at, referred_by) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, joined_at, expire_at, referred_by)
            )
            await db.commit()
            if referred_by:
                await increment_referral(referred_by)
            return True
        return False


async def increment_referral(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT referral_count FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            count = row[0] + 1
            await db.execute("UPDATE users SET referral_count = ? WHERE user_id = ?", (count, user_id))
            await db.commit()
            if count % 2 == 0:
                await extend_time(user_id, days=1)


async def extend_time(user_id: int, days: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT expire_at FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            current_expire = datetime.fromisoformat(row[0])
            base = max(current_expire, datetime.now())
            new_expire = base + timedelta(days=days)
            await db.execute("UPDATE users SET expire_at = ? WHERE user_id = ?", (new_expire.isoformat(), user_id))
            await db.commit()


async def get_remaining_days(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT expire_at FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            expire = datetime.fromisoformat(row[0])
            remaining = (expire - datetime.now()).days
            return max(remaining, 0)
        return 0


async def get_channels(channel_type: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if channel_type:
            cursor = await db.execute("SELECT channel_id FROM channels WHERE type = ?", (channel_type,))
        else:
            cursor = await db.execute("SELECT channel_id FROM channels")
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def get_channels_full(channel_type: str = None):
    """channel_id va invite_link bilan birga qaytaradi"""
    async with aiosqlite.connect(DB_NAME) as db:
        if channel_type:
            cursor = await db.execute("SELECT channel_id, invite_link FROM channels WHERE type = ?", (channel_type,))
        else:
            cursor = await db.execute("SELECT channel_id, invite_link FROM channels")
        return await cursor.fetchall()


async def add_channel(channel_id: str, channel_type: str, invite_link: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO channels (channel_id, type, invite_link) VALUES (?, ?, ?)",
            (channel_id, channel_type, invite_link)
        )
        await db.commit()


async def remove_channel(channel_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        await db.commit()


async def is_admin(user_id: int, owner_id: int) -> bool:
    if user_id == owner_id:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row is not None


async def add_admin(user_id: int, added_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)", (user_id, added_by))
        await db.commit()


async def remove_admin(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_admins():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, added_by FROM admins")
        return await cursor.fetchall()
