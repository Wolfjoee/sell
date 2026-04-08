import aiosqlite
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Initialize database with all required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Coupons table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS coupons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    price REAL NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Coupon codes table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS coupon_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coupon_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    is_used INTEGER DEFAULT 0,
                    used_by INTEGER,
                    used_at TIMESTAMP,
                    FOREIGN KEY (coupon_id) REFERENCES coupons(id),
                    FOREIGN KEY (used_by) REFERENCES users(id),
                    UNIQUE(coupon_id, code)
                )
            ''')

            # Orders table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    coupon_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    total_price REAL NOT NULL,
                    utr TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (coupon_id) REFERENCES coupons(id)
                )
            ''')

            # Settings table for UPI and other configs
            await db.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.commit()
            logger.info("Database initialized successfully")

    # User operations
    async def add_user(self, telegram_id: int, username: str = None, first_name: str = None):
        """Add or update user"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users (telegram_id, username, first_name)
                VALUES (?, ?, ?)
            ''', (telegram_id, username, first_name))
            await db.commit()

    async def get_all_users(self) -> List[int]:
        """Get all user telegram IDs"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT telegram_id FROM users') as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    # Coupon operations
    async def add_coupon(self, name: str, price: float) -> bool:
        """Add new coupon"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO coupons (name, price) VALUES (?, ?)
                ''', (name, price))
                await db.commit()
                return True
        except aiosqlite.IntegrityError:
            return False

    async def get_all_coupons(self) -> List[Dict]:
        """Get all active coupons with stock count"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT c.id, c.name, c.price,
                       COUNT(CASE WHEN cc.is_used = 0 THEN 1 END) as available_codes
                FROM coupons c
                LEFT JOIN coupon_codes cc ON c.id = cc.coupon_id
                WHERE c.is_active = 1
                GROUP BY c.id, c.name, c.price
            ''') as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        'id': row[0],
                        'name': row[1],
                        'price': row[2],
                        'stock': row[3]
                    }
                    for row in rows
                ]

    async def get_coupon_by_id(self, coupon_id: int) -> Optional[Dict]:
        """Get coupon details by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT c.id, c.name, c.price,
                       COUNT(CASE WHEN cc.is_used = 0 THEN 1 END) as available_codes
                FROM coupons c
                LEFT JOIN coupon_codes cc ON c.id = cc.coupon_id
                WHERE c.id = ? AND c.is_active = 1
                GROUP BY c.id
            ''', (coupon_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'name': row[1],
                        'price': row[2],
                        'stock': row[3]
                    }
                return None

    async def get_coupon_by_name(self, name: str) -> Optional[Dict]:
        """Get coupon details by name"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT c.id, c.name, c.price,
                       COUNT(CASE WHEN cc.is_used = 0 THEN 1 END) as available_codes
                FROM coupons c
                LEFT JOIN coupon_codes cc ON c.id = cc.coupon_id
                WHERE c.name = ? AND c.is_active = 1
                GROUP BY c.id
            ''', (name,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'name': row[1],
                        'price': row[2],
                        'stock': row[3]
                    }
                return None

    # Coupon code operations
    async def add_coupon_codes(self, coupon_id: int, codes: List[str]) -> Tuple[int, int]:
        """Add multiple codes for a coupon. Returns (added, duplicates)"""
        added = 0
        duplicates = 0
        async with aiosqlite.connect(self.db_path) as db:
            for code in codes:
                try:
                    await db.execute('''
                        INSERT INTO coupon_codes (coupon_id, code)
                        VALUES (?, ?)
                    ''', (coupon_id, code.strip()))
                    added += 1
                except aiosqlite.IntegrityError:
                    duplicates += 1
            await db.commit()
        return added, duplicates

    async def get_available_codes(self, coupon_id: int, quantity: int) -> List[str]:
        """Get available unused codes for a coupon"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT code FROM coupon_codes
                WHERE coupon_id = ? AND is_used = 0
                LIMIT ?
            ''', (coupon_id, quantity)) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def mark_codes_as_used(self, coupon_id: int, codes: List[str], user_id: int):
        """Mark codes as used"""
        async with aiosqlite.connect(self.db_path) as db:
            for code in codes:
                await db.execute('''
                    UPDATE coupon_codes
                    SET is_used = 1, used_by = ?, used_at = CURRENT_TIMESTAMP
                    WHERE coupon_id = ? AND code = ?
                ''', (user_id, coupon_id, code))
            await db.commit()

    async def get_code_count(self, coupon_id: int) -> Tuple[int, int]:
        """Get total and available code count. Returns (total, available)"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN is_used = 0 THEN 1 END) as available
                FROM coupon_codes
                WHERE coupon_id = ?
            ''', (coupon_id,)) as cursor:
                row = await cursor.fetchone()
                return (row[0], row[1]) if row else (0, 0)

    # Order operations
    async def create_order(self, user_id: int, coupon_id: int, quantity: int,
                          total_price: float, utr: str) -> str:
        """Create new order and return order number"""
        order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO orders (order_number, user_id, coupon_id, quantity, total_price, utr, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            ''', (order_number, user_id, coupon_id, quantity, total_price, utr))
            await db.commit()
        return order_number

    async def get_order(self, order_id: int) -> Optional[Dict]:
        """Get order details by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT o.id, o.order_number, o.user_id, u.telegram_id, u.username,
                       c.name, o.quantity, o.total_price, o.utr, o.status,
                       o.created_at, o.updated_at, c.id as coupon_id
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN coupons c ON o.coupon_id = c.id
                WHERE o.id = ?
            ''', (order_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'order_number': row[1],
                        'user_id': row[2],
                        'telegram_id': row[3],
                        'username': row[4],
                        'coupon_name': row[5],
                        'quantity': row[6],
                        'total_price': row[7],
                        'utr': row[8],
                        'status': row[9],
                        'created_at': row[10],
                        'updated_at': row[11],
                        'coupon_id': row[12]
                    }
                return None

    async def get_order_by_number(self, order_number: str) -> Optional[Dict]:
        """Get order details by order number"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT o.id, o.order_number, o.user_id, u.telegram_id, u.username,
                       c.name, o.quantity, o.total_price, o.utr, o.status,
                       o.created_at, o.updated_at, c.id as coupon_id
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN coupons c ON o.coupon_id = c.id
                WHERE o.order_number = ?
            ''', (order_number,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'order_number': row[1],
                        'user_id': row[2],
                        'telegram_id': row[3],
                        'username': row[4],
                        'coupon_name': row[5],
                        'quantity': row[6],
                        'total_price': row[7],
                        'utr': row[8],
                        'status': row[9],
                        'created_at': row[10],
                        'updated_at': row[11],
                        'coupon_id': row[12]
                    }
                return None

    async def get_user_orders(self, telegram_id: int) -> List[Dict]:
        """Get all orders for a user"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT o.order_number, c.name, o.quantity, o.total_price,
                       o.status, o.created_at
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN coupons c ON o.coupon_id = c.id
                WHERE u.telegram_id = ?
                ORDER BY o.created_at DESC
            ''', (telegram_id,)) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        'order_number': row[0],
                        'coupon_name': row[1],
                        'quantity': row[2],
                        'total_price': row[3],
                        'status': row[4],
                        'created_at': row[5]
                    }
                    for row in rows
                ]

    async def get_all_orders(self, status: str = None) -> List[Dict]:
        """Get all orders, optionally filtered by status"""
        async with aiosqlite.connect(self.db_path) as db:
            query = '''
                SELECT o.id, o.order_number, u.username, c.name, o.quantity,
                       o.total_price, o.utr, o.status, o.created_at
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN coupons c ON o.coupon_id = c.id
            '''
            params = []
            if status:
                query += ' WHERE o.status = ?'
                params.append(status)
            query += ' ORDER BY o.created_at DESC'

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        'id': row[0],
                        'order_number': row[1],
                        'username': row[2],
                        'coupon_name': row[3],
                        'quantity': row[4],
                        'total_price': row[5],
                        'utr': row[6],
                        'status': row[7],
                        'created_at': row[8]
                    }
                    for row in rows
                ]

    async def update_order_status(self, order_id: int, status: str):
        """Update order status"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE orders
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, order_id))
            await db.commit()

    async def check_duplicate_utr(self, utr: str) -> bool:
        """Check if UTR already exists in pending/approved orders"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT COUNT(*) FROM orders
                WHERE utr = ? AND status IN ('pending', 'approved', 'delivered')
            ''', (utr,)) as cursor:
                row = await cursor.fetchone()
                return row[0] > 0

    # Settings operations
    async def set_setting(self, key: str, value: str):
        """Set a setting value"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            await db.commit()

    async def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT value FROM settings WHERE key = ?
            ''', (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None


# Global database instance
db = Database()