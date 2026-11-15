import asyncpg
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Создает пул соединений и инициализирует таблицы."""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.db_url,
                ssl='require',
                min_size=2,
                max_size=10
            )
            logger.info("Успешное подключение к базе данных.")
            await self._create_tables()
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise

    async def close(self):
        """Закрывает пул соединений."""
        if self.pool:
            await self.pool.close()
            logger.info("Соединение с базой данных закрыто.")

    async def _create_tables(self):
        """Создает все необходимые таблицы и обновляет структуру."""
        async with self.pool.acquire() as conn:
            # 1. Таблица паспортов (создается, если нет)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS passports (
                    user_id BIGINT PRIMARY KEY,
                    balance BIGINT DEFAULT 0,
                    signature_url TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # 2. АВТОМАТИЧЕСКАЯ МИГРАЦИЯ ПАСПОРТОВ (Убирает NOT NULL)
            try:
                await conn.execute("""
                    DO $$
                    DECLARE
                        r RECORD;
                    BEGIN
                        FOR r IN 
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'passports' 
                              AND column_name != 'user_id' 
                              AND is_nullable = 'NO'
                        LOOP
                            EXECUTE 'ALTER TABLE passports ALTER COLUMN ' || quote_ident(r.column_name) || ' DROP NOT NULL';
                        END LOOP;
                    END $$;
                """)
                logger.info("Миграция паспортов: ограничения NOT NULL сняты.")
            except Exception as e:
                logger.warning(f"Миграция паспортов: {e}")
            
            # Добавляем колонку для подписи, если ее еще нет
            await conn.execute("""
                ALTER TABLE passports ADD COLUMN IF NOT EXISTS signature_url TEXT;
            """)
            
            # 3. Таблица инвентаря (для магазина)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES passports(user_id) ON DELETE CASCADE,
                    item_name TEXT NOT NULL,
                    quantity INT DEFAULT 1
                );
            """)
            
            # 4. Таблица персонажей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    user_id BIGINT PRIMARY KEY REFERENCES passports(user_id) ON DELETE CASCADE,
                    char_name TEXT,
                    char_data JSONB
                );
            """)

            # 5. ТАБЛИЦА: Настройки серверов
            # Создаем, если нет
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    settings JSONB DEFAULT '{}'::jsonb
                );
            """)
            # ПРИНУДИТЕЛЬНО добавляем колонку settings, если таблица старая и в ней её нет
            await conn.execute("""
                ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'::jsonb;
            """)
            
            logger.info("Таблицы проверены/созданы.")

    # ==================== НАСТРОЙКИ СЕРВЕРА ====================

    async def get_guild_settings(self, guild_id: int) -> dict:
        """Получает настройки сервера в виде словаря."""
        async with self.pool.acquire() as conn:
            # Убедимся, что запись существует, чтобы не было ошибок
            await conn.execute("INSERT INTO guild_settings (guild_id) VALUES ($1) ON CONFLICT DO NOTHING", guild_id)
            
            row = await conn.fetchrow("SELECT settings FROM guild_settings WHERE guild_id = $1", guild_id)
            if row and row['settings']:
                return dict(row['settings'])
            return {}

    async def update_guild_settings(self, guild_id: int, settings: dict) -> None:
        """Обновляет настройки сервера (объединяет со старыми)."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO guild_settings (guild_id, settings)
                VALUES ($1, $2::jsonb)
                ON CONFLICT (guild_id) DO UPDATE 
                SET settings = guild_settings.settings || $2::jsonb
            """, guild_id, settings)

    # ==================== МЕТОДЫ ПАСПОРТА И БАЛАНСА ====================
    
    async def get_passport(self, user_id: int) -> Optional[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM passports WHERE user_id = $1", user_id)

    async def create_passport(self, user_id: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)

    async def get_balance(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            row = await conn.fetchval("SELECT balance FROM passports WHERE user_id = $1", user_id)
            return row if row is not None else 0

    async def update_balance(self, user_id: int, amount: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            await conn.execute("UPDATE passports SET balance = balance + $1 WHERE user_id = $2", amount, user_id)

    async def set_balance(self, user_id: int, amount: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            await conn.execute("UPDATE passports SET balance = $1 WHERE user_id = $2", amount, user_id)

    # ==================== ПОДПИСИ (СИГНАТУРЫ) ====================

    async def set_user_signature(self, user_id: int, signature_url: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            await conn.execute("UPDATE passports SET signature_url = $1 WHERE user_id = $2", signature_url, user_id)

    async def get_user_signature(self, user_id: int) -> Optional[str]:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("SELECT signature_url FROM passports WHERE user_id = $1", user_id)

    # ==================== МЕТОДЫ ИНВЕНТАРЯ ====================

    async def add_item(self, user_id: int, item_name: str, quantity: int = 1) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            existing = await conn.fetchval("SELECT id FROM inventory WHERE user_id = $1 AND item_name = $2", user_id, item_name)
            if existing:
                await conn.execute("UPDATE inventory SET quantity = quantity + $1 WHERE id = $2", quantity, existing)
            else:
                await conn.execute("INSERT INTO inventory (user_id, item_name, quantity) VALUES ($1, $2, $3)", user_id, item_name, quantity)

    async def remove_item(self, user_id: int, item_name: str, quantity: int = 1) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, quantity FROM inventory WHERE user_id = $1 AND item_name = $2", user_id, item_name)
            if not row or row['quantity'] < quantity:
                return False
            
            new_qty = row['quantity'] - quantity
            if new_qty <= 0:
                await conn.execute("DELETE FROM inventory WHERE id = $1", row['id'])
            else:
                await conn.execute("UPDATE inventory SET quantity = $1 WHERE id = $2", new_qty, row['id'])
            return True

    async def get_inventory(self, user_id: int) -> List[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT item_name, quantity FROM inventory WHERE user_id = $1 ORDER BY item_name", user_id)

    # ==================== ПЕРСОНАЖИ ====================

    async def get_character(self, user_id: int) -> Optional[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM characters WHERE user_id = $1", user_id)

    async def save_character(self, user_id: int, name: str, data: Dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)
            await conn.execute("""
                INSERT INTO characters (user_id, char_name, char_data) 
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (user_id) DO UPDATE 
                SET char_name = $2, char_data = $3::jsonb
            """, user_id, name, data)