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
            # Таблица паспортов (пользователи)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS passports (
                    user_id BIGINT PRIMARY KEY,
                    balance BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # Добавляем колонку для подписи, если ее еще нет
            await conn.execute("""
                ALTER TABLE passports ADD COLUMN IF NOT EXISTS signature_url TEXT;
            """)
            
            # Таблица инвентаря (для магазина)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES passports(user_id) ON DELETE CASCADE,
                    item_name TEXT NOT NULL,
                    quantity INT DEFAULT 1
                );
            """)
            
            # Таблица персонажей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    user_id BIGINT PRIMARY KEY REFERENCES passports(user_id) ON DELETE CASCADE,
                    char_name TEXT,
                    char_data JSONB
                );
            """)
            logger.info("Таблицы проверены/созданы.")

    # ==================== МЕТОДЫ ПАСПОРТА И БАЛАНСА ====================
    
    async def get_passport(self, user_id: int) -> Optional[asyncpg.Record]:
        """Получает паспорт пользователя. Если нет - возвращает None."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM passports WHERE user_id = $1", user_id
            )

    async def create_passport(self, user_id: int) -> None:
        """Создает паспорт, если его нет."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )

    async def get_balance(self, user_id: int) -> int:
        """Получает баланс пользователя (создает паспорт при необходимости)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            row = await conn.fetchval(
                "SELECT balance FROM passports WHERE user_id = $1", user_id
            )
            return row if row is not None else 0

    async def update_balance(self, user_id: int, amount: int) -> None:
        """Изменяет баланс (amount может быть отрицательным)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            await conn.execute(
                "UPDATE passports SET balance = balance + $1 WHERE user_id = $2",
                amount, user_id
            )

    async def set_balance(self, user_id: int, amount: int) -> None:
        """Устанавливает точный баланс."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            await conn.execute(
                "UPDATE passports SET balance = $1 WHERE user_id = $2",
                amount, user_id
            )

    # ==================== ПОДПИСИ (СИГНАТУРЫ) ====================

    async def set_user_signature(self, user_id: int, signature_url: str) -> None:
        """Устанавливает URL подписи для пользователя."""
        async with self.pool.acquire() as conn:
            # Убедимся, что пользователь существует
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            await conn.execute(
                "UPDATE passports SET signature_url = $1 WHERE user_id = $2",
                signature_url, user_id
            )

    async def get_user_signature(self, user_id: int) -> Optional[str]:
        """Получает URL подписи пользователя."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT signature_url FROM passports WHERE user_id = $1", user_id
            )

    # ==================== МЕТОДЫ ИНВЕНТАРЯ ====================

    async def add_item(self, user_id: int, item_name: str, quantity: int = 1) -> None:
        """Добавляет предмет в инвентарь."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            existing = await conn.fetchval(
                "SELECT id FROM inventory WHERE user_id = $1 AND item_name = $2",
                user_id, item_name
            )
            if existing:
                await conn.execute(
                    "UPDATE inventory SET quantity = quantity + $1 WHERE id = $2",
                    quantity, existing
                )
            else:
                await conn.execute(
                    "INSERT INTO inventory (user_id, item_name, quantity) VALUES ($1, $2, $3)",
                    user_id, item_name, quantity
                )

    async def remove_item(self, user_id: int, item_name: str, quantity: int = 1) -> bool:
        """Удаляет предмет. Возвращает True, если успешно."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, quantity FROM inventory WHERE user_id = $1 AND item_name = $2",
                user_id, item_name
            )
            if not row or row['quantity'] < quantity:
                return False
            
            new_qty = row['quantity'] - quantity
            if new_qty <= 0:
                await conn.execute("DELETE FROM inventory WHERE id = $1", row['id'])
            else:
                await conn.execute("UPDATE inventory SET quantity = $1 WHERE id = $2", new_qty, row['id'])
            return True

    async def get_inventory(self, user_id: int) -> List[asyncpg.Record]:
        """Возвращает список предметов пользователя."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT item_name, quantity FROM inventory WHERE user_id = $1 ORDER BY item_name",
                user_id
            )

    # ==================== ПЕРСОНАЖИ ====================

    async def get_character(self, user_id: int) -> Optional[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM characters WHERE user_id = $1", user_id
            )

    async def save_character(self, user_id: int, name: str, data: Dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO passports (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id
            )
            await conn.execute("""
                INSERT INTO characters (user_id, char_name, char_data) 
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (user_id) DO UPDATE 
                SET char_name = $2, char_data = $3::jsonb
            """, user_id, name, data)
