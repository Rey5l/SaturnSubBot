"""Работа с SQLite: пользователи и баланс."""
import aiosqlite
from config import DB_PATH

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


async def init_db() -> None:
    """Создание таблиц при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL NOT NULL DEFAULT 0,
                referrer_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (referrer_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                asset TEXT NOT NULL,
                spend_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT NOT NULL,
                channel_id TEXT,
                title TEXT,
                reward REAL NOT NULL DEFAULT 0,
                platform TEXT NOT NULL DEFAULT 'tgrassa',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_completed_tasks (
                user_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, task_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (task_id) REFERENCES channel_tasks(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS flyer_pending_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                signature TEXT NOT NULL,
                price REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS flyer_completed_tasks (
                user_id INTEGER NOT NULL,
                signature TEXT NOT NULL,
                price REAL NOT NULL,
                completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, signature)
            )
        """)
        await db.commit()

    # Миграция: referrer_id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = [row[1] for row in await cur.fetchall()]
        if "referrer_id" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
            await db.commit()

    # Миграция: channel_tasks, user_completed_tasks
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='channel_tasks'"
        ) as cur:
            if await cur.fetchone() is None:
                await db.execute("""
                    CREATE TABLE channel_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_username TEXT NOT NULL,
                        channel_id TEXT,
                        title TEXT,
                        reward REAL NOT NULL DEFAULT 0,
                        platform TEXT NOT NULL DEFAULT 'tgrassa',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.execute("""
                    CREATE TABLE user_completed_tasks (
                        user_id INTEGER NOT NULL,
                        task_id INTEGER NOT NULL,
                        completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (user_id, task_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (task_id) REFERENCES channel_tasks(id)
                    )
                """)
                await db.commit()
    # Миграция: flyer_pending_tasks, flyer_completed_tasks
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='flyer_pending_tasks'"
        ) as cur:
            if await cur.fetchone() is None:
                await db.execute("""
                    CREATE TABLE flyer_pending_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        signature TEXT NOT NULL,
                        price REAL NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.execute("""
                    CREATE TABLE flyer_completed_tasks (
                        user_id INTEGER NOT NULL,
                        signature TEXT NOT NULL,
                        price REAL NOT NULL,
                        completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (user_id, signature)
                    )
                """)
                await db.commit()
    # Миграция: tgrassa_pending_tasks, tgrassa_completed_tasks
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tgrassa_pending_tasks'"
        ) as cur:
            if await cur.fetchone() is None:
                await db.execute("""
                    CREATE TABLE tgrassa_pending_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        signature TEXT NOT NULL,
                        price REAL NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.execute("""
                    CREATE TABLE tgrassa_completed_tasks (
                        user_id INTEGER NOT NULL,
                        signature TEXT NOT NULL,
                        price REAL NOT NULL,
                        completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (user_id, signature)
                    )
                """)
                await db.commit()
    # Миграция: grs_pending_credit (сумма к начислению за Grs при следующей успешной проверке)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='grs_pending_credit'"
        ) as cur:
            if await cur.fetchone() is None:
                await db.execute("""
                    CREATE TABLE grs_pending_credit (
                        user_id INTEGER PRIMARY KEY,
                        amount REAL NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.commit()
    # Миграция: frozen_funds (замороженные средства на 24 ч)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='frozen_funds'"
        ) as cur:
            if await cur.fetchone() is None:
                await db.execute("""
                    CREATE TABLE frozen_funds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        amount REAL NOT NULL,
                        unfreeze_at TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        signature TEXT,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.commit()


async def get_or_create_user(
    user_id: int,
    username: str | None = None,
    referrer_id: int | None = None,
) -> dict:
    """Получить пользователя или создать. referrer_id сохраняется только при создании."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return dict(row)
        await db.execute(
            """INSERT INTO users (user_id, username, balance, referrer_id)
               VALUES (?, ?, 0, ?)""",
            (user_id, username or "", referrer_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            return dict(await cur.fetchone())


async def get_balance(user_id: int) -> float:
    """Баланс пользователя (в условных единицах, привязанных к выводу)."""
    user = await get_or_create_user(user_id)
    return float(user["balance"])


async def add_balance(user_id: int, amount: float) -> float:
    """Зачислить пользователю amount. Возвращает новый баланс."""
    if amount <= 0:
        raise ValueError("Сумма должна быть больше 0")
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return float(row[0])


async def deduct_balance(user_id: int, amount: float) -> float:
    """Списать amount с баланса. Возвращает новый баланс. При недостатке — ValueError."""
    current = await get_balance(user_id)
    if current < amount:
        raise ValueError("Недостаточно средств на балансе")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (amount, user_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return float(row[0])


async def save_withdrawal(
    user_id: int, amount: float, asset: str, spend_id: str, status: str = "completed"
) -> None:
    """Сохранить запись о выводе."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO withdrawals (user_id, amount, asset, spend_id, status)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, amount, asset, spend_id, status),
        )
        await db.commit()


async def withdrawal_exists(spend_id: str) -> bool:
    """Проверить, использовался ли уже spend_id (идемпотентность)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM withdrawals WHERE spend_id = ?", (spend_id,)
        ) as cur:
            return (await cur.fetchone()) is not None


async def get_referrer_id(user_id: int) -> int | None:
    """ID реферера пользователя или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    return None


async def count_referrals(user_id: int) -> int:
    """Количество приглашённых пользователей (рефералов)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def stats_total_users() -> int:
    """Всего пользователей."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def stats_users_today() -> int:
    """Пользователей зарегистрировано сегодня."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def stats_tasks_completed() -> int:
    """Выполнено заданий (считаем как количество успешных выводов)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM withdrawals WHERE status = 'completed'"
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def stats_withdrawn_total() -> float:
    """Выведено всего (в условных единицах/USD)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM withdrawals WHERE status = 'completed'"
        ) as cur:
            row = await cur.fetchone()
    return float(row[0]) if row else 0.0


async def stats_withdrawn_today() -> float:
    """Выведено за сегодня."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM withdrawals
               WHERE status = 'completed' AND date(created_at) = date('now')"""
        ) as cur:
            row = await cur.fetchone()
    return float(row[0]) if row else 0.0


# --- Задания на подписку (каналы) ---

async def get_channel_tasks(platform: str | None = None, active_only: bool = True) -> list[dict]:
    """Список заданий-каналов. platform: 'tgrassa' | 'flyer' | None (все)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM channel_tasks WHERE 1=1"
        params: list = []
        if platform:
            sql += " AND LOWER(platform) = LOWER(?)"
            params.append(platform)
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY platform, id"
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_channel_task(task_id: int) -> dict | None:
    """Задание по id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channel_tasks WHERE id = ?", (task_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def user_has_completed_task(user_id: int, task_id: int) -> bool:
    """Пользователь уже выполнил это задание."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM user_completed_tasks WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        ) as cur:
            return (await cur.fetchone()) is not None


async def complete_channel_task(user_id: int, task_id: int, reward: float) -> None:
    """Отметить задание выполненным и зачислить награду."""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_completed_tasks (user_id, task_id) VALUES (?, ?)",
            (user_id, task_id),
        )
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (reward, user_id),
        )
        await db.commit()


async def add_channel_task(
    channel_username: str,
    reward: float,
    platform: str = "tgrassa",
    title: str | None = None,
    channel_id: str | None = None,
) -> int:
    """Добавить задание-канал. Возвращает id."""
    username = channel_username.lstrip("@").strip()
    if not username or reward <= 0:
        raise ValueError("Укажите username канала и награду > 0")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO channel_tasks (channel_username, channel_id, title, reward, platform)
               VALUES (?, ?, ?, ?, ?)""",
            (username, channel_id or "", title or "", reward, platform.lower()),
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def stats_tasks_completed_channels() -> int:
    """Количество выполненных заданий (каналы + Flyer + Tgrassa)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM user_completed_tasks") as cur:
            r1 = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM flyer_completed_tasks") as cur:
            r2 = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tgrassa_completed_tasks") as cur:
            r3 = (await cur.fetchone())[0]
    return (r1 or 0) + (r2 or 0) + (r3 or 0)


# --- Flyer API: pending/completed по signature ---

async def flyer_save_pending(user_id: int, signature: str, price: float) -> int:
    """Сохранить задание Flyer для пользователя (перед показом). Возвращает id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO flyer_pending_tasks (user_id, signature, price)
               VALUES (?, ?, ?)""",
            (user_id, signature, price),
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def flyer_get_pending_by_id(pending_id: int) -> dict | None:
    """Получить запись pending по id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM flyer_pending_tasks WHERE id = ?", (pending_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def flyer_get_pending_by_user(user_id: int) -> list[dict]:
    """Все pending-задания Flyer для пользователя (для массовой проверки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM flyer_pending_tasks WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def flyer_already_completed(user_id: int, signature: str) -> bool:
    """Пользователь уже получил награду за это задание Flyer."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM flyer_completed_tasks WHERE user_id = ? AND signature = ?",
            (user_id, signature),
        ) as cur:
            return (await cur.fetchone()) is not None


async def flyer_mark_completed_and_credit(user_id: int, signature: str, price: float) -> None:
    """Зачислить награду и отметить задание выполненным; удалить из pending."""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO flyer_completed_tasks (user_id, signature, price) VALUES (?, ?, ?)",
            (user_id, signature, price),
        )
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (price, user_id),
        )
        await db.execute("DELETE FROM flyer_pending_tasks WHERE user_id = ? AND signature = ?", (user_id, signature))
        await db.commit()


async def flyer_mark_completed_and_freeze(user_id: int, signature: str, payout: float, unfreeze_at: str) -> None:
    """Отметить задание выполненным и заморозить выплату до unfreeze_at; удалить из pending."""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO flyer_completed_tasks (user_id, signature, price) VALUES (?, ?, ?)",
            (user_id, signature, payout),
        )
        await db.execute(
            """INSERT INTO frozen_funds (user_id, amount, unfreeze_at, platform, signature, created_at)
               VALUES (?, ?, ?, 'flyer', ?, datetime('now'))""",
            (user_id, payout, unfreeze_at, signature),
        )
        await db.execute("DELETE FROM flyer_pending_tasks WHERE user_id = ? AND signature = ?", (user_id, signature))
        await db.commit()


# --- Tgrassa API: pending/completed по signature ---

async def tgrassa_save_pending(user_id: int, signature: str, price: float) -> int:
    """Сохранить задание Tgrassa для пользователя. Возвращает id."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO tgrassa_pending_tasks (user_id, signature, price)
               VALUES (?, ?, ?)""",
            (user_id, signature, price),
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def tgrassa_get_pending_by_id(pending_id: int) -> dict | None:
    """Получить запись pending по id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tgrassa_pending_tasks WHERE id = ?", (pending_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def tgrassa_already_completed(user_id: int, signature: str) -> bool:
    """Пользователь уже получил награду за это задание Tgrassa."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM tgrassa_completed_tasks WHERE user_id = ? AND signature = ?",
            (user_id, signature),
        ) as cur:
            return (await cur.fetchone()) is not None


async def tgrassa_mark_completed_and_credit(user_id: int, signature: str, price: float) -> None:
    """Зачислить награду и отметить задание Tgrassa выполненным."""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tgrassa_completed_tasks (user_id, signature, price) VALUES (?, ?, ?)",
            (user_id, signature, price),
        )
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (price, user_id),
        )
        await db.execute("DELETE FROM tgrassa_pending_tasks WHERE user_id = ? AND signature = ?", (user_id, signature))
        await db.commit()


# --- Grs: сумма к начислению при успешной проверке подписки ---

async def grs_set_pending_credit(user_id: int, amount: float) -> None:
    """Сохранить сумму к начислению за Grs при следующей успешной проверке."""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO grs_pending_credit (user_id, amount, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET amount = ?, updated_at = datetime('now')""",
            (user_id, amount, amount),
        )
        await db.commit()


async def grs_take_pending_amount(user_id: int) -> float:
    """Взять сохранённую сумму и обнулить (без начисления). Возвращает сумму для заморозки."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT amount FROM grs_pending_credit WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    amount = float(row[0]) if row and row[0] else 0.0
    if amount <= 0:
        return 0.0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM grs_pending_credit WHERE user_id = ?", (user_id,))
        await db.commit()
    return amount


async def grs_clear_pending_credit(user_id: int) -> None:
    """Обнулить сохранённую сумму (без начисления)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM grs_pending_credit WHERE user_id = ?", (user_id,))
        await db.commit()


# --- Замороженные средства (24 ч), разморозка с проверкой подписки ---

async def frozen_add(user_id: int, amount: float, unfreeze_at: str, platform: str, signature: str | None = None) -> None:
    """Добавить сумму в заморозку. unfreeze_at — datetime в формате SQLite."""
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO frozen_funds (user_id, amount, unfreeze_at, platform, signature, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (user_id, amount, unfreeze_at, platform, signature or None),
        )
        await db.commit()


async def frozen_get_total(user_id: int) -> float:
    """Сумма замороженных средств пользователя (unfreeze_at > сейчас)."""
    from datetime import datetime
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM frozen_funds WHERE user_id = ? AND unfreeze_at > ?",
            (user_id, now),
        ) as cur:
            row = await cur.fetchone()
    return float(row[0]) if row else 0.0


async def frozen_get_summary(user_id: int) -> tuple[float, str | None]:
    """(сумма замороженного, ближайшая дата разморозки или None)."""
    from datetime import datetime
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT SUM(amount), MIN(unfreeze_at) FROM frozen_funds WHERE user_id = ? AND unfreeze_at > ?",
            (user_id, now),
        ) as cur:
            row = await cur.fetchone()
    total = float(row[0]) if row and row[0] is not None else 0.0
    min_at = row[1] if row and row[1] else None
    return total, min_at


async def frozen_get_due() -> list[dict]:
    """Список записей, у которых unfreeze_at <= сейчас (пора размораживать)."""
    from datetime import datetime
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, user_id, amount, platform, signature FROM frozen_funds WHERE unfreeze_at <= ?",
            (now,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def frozen_release_and_credit(row_id: int) -> tuple[int, float] | None:
    """Зачислить сумму на баланс и удалить запись. Возвращает (user_id, amount) или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, amount FROM frozen_funds WHERE id = ?", (row_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    user_id, amount = int(row[0]), float(row[1])
    await get_or_create_user(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.execute("DELETE FROM frozen_funds WHERE id = ?", (row_id,))
        await db.commit()
    return (user_id, amount)


async def frozen_delete(row_id: int) -> None:
    """Удалить запись о заморозке без начисления."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM frozen_funds WHERE id = ?", (row_id,))
        await db.commit()
