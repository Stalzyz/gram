"""PostgreSQL store: tracks per-profile status (pending/success/failed) and
holds the final result row for each profile, so the pipeline can save
progress after every profile and resume after an interruption."""
import os
import json
from datetime import datetime, timezone
import psycopg2
from psycopg2 import pool
from utils.logger import get_logger

logger = get_logger()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    credits INTEGER NOT NULL DEFAULT 0,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    campaign TEXT NOT NULL,
    username TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    error TEXT,
    updated_at TEXT,
    PRIMARY KEY (user_id, campaign, username)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount_cents INTEGER NOT NULL,
    credits INTEGER NOT NULL,
    gateway TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    min_followers INTEGER NOT NULL DEFAULT 0,
    max_followers INTEGER,
    location_keywords TEXT,
    require_shopify BOOLEAN NOT NULL DEFAULT FALSE,
    require_woocommerce BOOLEAN NOT NULL DEFAULT FALSE,
    require_meta_pixel BOOLEAN NOT NULL DEFAULT FALSE,
    target_categories TEXT,
    require_website BOOLEAN NOT NULL DEFAULT FALSE,
    deep_enrichment BOOLEAN NOT NULL DEFAULT FALSE
);
"""

class ResultStore:
    """Thread-safe wrapper around PostgreSQL using connection pooling."""

    def __init__(self, db_path: str = None):
        # Ignore the old SQLite db_path and use the environment variable
        self.db_url = os.environ.get("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable is missing. Postgres is required.")
        
        # Connection pool to safely handle multithreaded workers
        self.pool = psycopg2.pool.ThreadedConnectionPool(1, 20, self.db_url)
        self._init_schema()

    def _init_schema(self):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
                # Ensure is_admin column exists if table was already created
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS max_followers INTEGER")
                cur.execute("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS location_keywords TEXT")
                cur.execute("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS require_shopify BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS require_woocommerce BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS require_meta_pixel BOOLEAN NOT NULL DEFAULT FALSE")
                cur.execute("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS target_categories TEXT")
            conn.commit()
        finally:
            self.pool.putconn(conn)

    # --- USER METHODS ---
    def create_user(self, email: str, hashed_password: str) -> int:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (email, hashed_password, created_at) VALUES (%s, %s, %s) RETURNING id",
                    (email, hashed_password, datetime.now(timezone.utc).isoformat())
                )
                user_id = cur.fetchone()[0]
            conn.commit()
            return user_id
        finally:
            self.pool.putconn(conn)

    def get_user_by_email(self, email: str) -> dict:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, hashed_password, credits, is_admin FROM users WHERE email = %s", (email,))
                row = cur.fetchone()
                if row:
                    return {"id": row[0], "email": row[1], "hashed_password": row[2], "credits": row[3], "is_admin": row[4]}
                return None
        finally:
            self.pool.putconn(conn)

    def get_user_by_id(self, user_id: int) -> dict:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, hashed_password, credits, is_admin FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    return {"id": row[0], "email": row[1], "hashed_password": row[2], "credits": row[3], "is_admin": row[4]}
                return None
        finally:
            self.pool.putconn(conn)

    def add_credits(self, user_id: int, amount: int):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET credits = credits + %s WHERE id = %s", (amount, user_id))
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def deduct_credits(self, user_id: int, amount: int) -> bool:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT credits FROM users WHERE id = %s", (user_id,))
                current = cur.fetchone()[0]
                if current < amount:
                    return False
                cur.execute("UPDATE users SET credits = credits - %s WHERE id = %s", (amount, user_id))
            conn.commit()
            return True
        finally:
            self.pool.putconn(conn)
            
    def make_admin(self, user_id: int):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_admin = TRUE WHERE id = %s", (user_id,))
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def get_user_preferences(self, user_id: int) -> dict:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT min_followers, require_website, deep_enrichment, max_followers, location_keywords, require_shopify, require_woocommerce, require_meta_pixel, target_categories FROM user_preferences WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "min_followers": row[0], "require_website": row[1], "deep_enrichment": row[2],
                        "max_followers": row[3], "location_keywords": row[4],
                        "require_shopify": row[5], "require_woocommerce": row[6],
                        "require_meta_pixel": row[7], "target_categories": row[8]
                    }
                return {
                    "min_followers": 0, "require_website": False, "deep_enrichment": False,
                    "max_followers": None, "location_keywords": None,
                    "require_shopify": False, "require_woocommerce": False,
                    "require_meta_pixel": False, "target_categories": None
                }
        finally:
            self.pool.putconn(conn)

    def set_user_preferences(self, user_id: int, prefs: dict):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO user_preferences (user_id, min_followers, require_website, deep_enrichment, max_followers, location_keywords, require_shopify, require_woocommerce, require_meta_pixel, target_categories) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (user_id) DO UPDATE SET 
                       min_followers = EXCLUDED.min_followers,
                       require_website = EXCLUDED.require_website,
                       deep_enrichment = EXCLUDED.deep_enrichment,
                       max_followers = EXCLUDED.max_followers,
                       location_keywords = EXCLUDED.location_keywords,
                       require_shopify = EXCLUDED.require_shopify,
                       require_woocommerce = EXCLUDED.require_woocommerce,
                       require_meta_pixel = EXCLUDED.require_meta_pixel,
                       target_categories = EXCLUDED.target_categories""",
                    (user_id, 
                     prefs.get("min_followers", 0), prefs.get("require_website", False), prefs.get("deep_enrichment", False), 
                     prefs.get("max_followers"), prefs.get("location_keywords"),
                     prefs.get("require_shopify", False), prefs.get("require_woocommerce", False),
                     prefs.get("require_meta_pixel", False), prefs.get("target_categories"))
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def get_user_campaigns(self, user_id: int) -> list:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT campaign, 
                              COUNT(*) as total,
                              SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                              SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                              SUM(CASE WHEN status LIKE 'skipped%' THEN 1 ELSE 0 END) as skipped,
                              MAX(updated_at) as last_updated
                       FROM profiles 
                       WHERE user_id = %s 
                       GROUP BY campaign
                       ORDER BY last_updated DESC""",
                    (user_id,)
                )
                return [
                    {
                        "campaign": r[0],
                        "total": r[1],
                        "success": r[2],
                        "failed": r[3],
                        "skipped": r[4],
                        "last_updated": r[5]
                    }
                    for r in cur.fetchall()
                ]
        finally:
            self.pool.putconn(conn)

    # --- ADMIN METHODS ---
    def get_setting(self, key: str, default: str = None) -> str:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cur.fetchone()
                return row[0] if row else default
        finally:
            self.pool.putconn(conn)

    def set_setting(self, key: str, value: str):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, value)
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def log_transaction(self, user_id: int, amount_cents: int, credits: int, gateway: str):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO transactions (user_id, amount_cents, credits, gateway, created_at) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, amount_cents, credits, gateway, datetime.now(timezone.utc).isoformat())
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def get_sales_stats(self) -> dict:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                total_users = cur.fetchone()[0]
                
                cur.execute("SELECT COALESCE(SUM(amount_cents), 0) FROM transactions")
                total_cents = cur.fetchone()[0]
                
                cur.execute("SELECT user_id, amount_cents, credits, gateway, created_at FROM transactions ORDER BY created_at DESC LIMIT 50")
                txs = [{"user_id": r[0], "amount_cents": r[1], "credits": r[2], "gateway": r[3], "created_at": r[4]} for r in cur.fetchall()]
                
                return {
                    "total_users": total_users,
                    "total_revenue_usd": total_cents / 100.0,
                    "recent_transactions": txs
                }
        finally:
            self.pool.putconn(conn)

    def get_customers(self) -> list:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.id, u.email, u.credits, u.created_at, 
                           COALESCE(SUM(t.amount_cents), 0) as total_spent
                    FROM users u
                    LEFT JOIN transactions t ON u.id = t.user_id
                    GROUP BY u.id
                    ORDER BY u.created_at DESC
                """)
                return [{
                    "id": r[0], "email": r[1], "credits": r[2],
                    "created_at": r[3].isoformat() if r[3] else None,
                    "total_spent_usd": r[4] / 100.0
                } for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def get_customer_invoice(self, customer_id: int) -> dict:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                # Get user info
                cur.execute("SELECT id, email, credits, created_at FROM users WHERE id = %s", (customer_id,))
                user = cur.fetchone()
                if not user:
                    return None
                # Get all transactions for this user
                cur.execute("""
                    SELECT id, amount_cents, credits, gateway, created_at
                    FROM transactions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (customer_id,))
                txs = [{
                    "id": r[0],
                    "amount_usd": r[1] / 100.0,
                    "credits": r[2],
                    "gateway": r[3],
                    "date": r[4].strftime("%d %b %Y %H:%M") if r[4] else "N/A"
                } for r in cur.fetchall()]
                total_spent = sum(t["amount_usd"] for t in txs)
                return {
                    "user_id": user[0],
                    "email": user[1],
                    "credits": user[2],
                    "member_since": user[3].strftime("%d %b %Y") if user[3] else "N/A",
                    "transactions": txs,
                    "total_spent_usd": total_spent
                }
        finally:
            self.pool.putconn(conn)

    # --- PROFILE METHODS ---
    def seed_pending(self, user_id: int, campaign: str, usernames: list):
        if not usernames:
            return
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                dt = datetime.now(timezone.utc).isoformat()
                # Create the values string securely
                args_str = ','.join(cur.mogrify("(%s, %s, %s, 'pending', %s)", (user_id, campaign, u, dt)).decode('utf-8') for u in usernames)
                cur.execute("INSERT INTO profiles (user_id, campaign, username, status, updated_at) VALUES " + args_str + " ON CONFLICT (user_id, campaign, username) DO NOTHING")
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def get_status(self, user_id: int, campaign: str, username: str) -> str:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM profiles WHERE user_id = %s AND campaign = %s AND username = %s", (user_id, campaign, username))
                row = cur.fetchone()
                return row[0] if row else "pending"
        finally:
            self.pool.putconn(conn)

    def mark_success(self, user_id: int, campaign: str, username: str, result: dict):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                dt = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """UPDATE profiles
                       SET status='success', result_json=%s, error=NULL,
                           attempts=attempts+1, updated_at=%s
                       WHERE user_id=%s AND campaign=%s AND username=%s""",
                    (json.dumps(result), dt, user_id, campaign, username),
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def mark_failed(self, user_id: int, campaign: str, username: str, error: str):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                dt = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """UPDATE profiles
                       SET status='failed', error=%s, attempts=attempts+1, updated_at=%s
                       WHERE user_id=%s AND campaign=%s AND username=%s""",
                    (error, dt, user_id, campaign, username),
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def mark_skipped(self, user_id: int, campaign: str, username: str, reason: str):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                dt = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """UPDATE profiles
                       SET status='skipped_' || %s, error=%s, attempts=attempts+1, updated_at=%s
                       WHERE user_id=%s AND campaign=%s AND username=%s""",
                    (reason, f"Skipped: {reason}", dt, user_id, campaign, username),
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def reset_all(self, user_id: int, campaign: str = None):
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                if campaign:
                    cur.execute("DELETE FROM profiles WHERE user_id=%s AND campaign=%s", (user_id, campaign))
                else:
                    cur.execute("DELETE FROM profiles WHERE user_id=%s", (user_id,))
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def pending_usernames(self, user_id: int, campaign: str) -> list:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT username FROM profiles WHERE user_id=%s AND campaign=%s AND status != 'success'", (user_id, campaign))
                return [r[0] for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def all_results(self, user_id: int, campaign: str) -> list:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT result_json FROM profiles WHERE user_id=%s AND campaign=%s AND status='success' AND result_json IS NOT NULL", (user_id, campaign))
                return [json.loads(r[0]) for r in cur.fetchall()]
        finally:
            self.pool.putconn(conn)

    def stats(self, user_id: int, campaign: str) -> dict:
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM profiles WHERE user_id=%s AND campaign=%s", (user_id, campaign))
                row = cur.fetchone(); total = row[0] if row else 0

                cur.execute("SELECT COUNT(*) FROM profiles WHERE user_id=%s AND campaign=%s AND status='success'", (user_id, campaign))
                row = cur.fetchone(); success = row[0] if row else 0

                cur.execute("SELECT COUNT(*) FROM profiles WHERE user_id=%s AND campaign=%s AND status='failed'", (user_id, campaign))
                row = cur.fetchone(); failed = row[0] if row else 0

                cur.execute("SELECT COUNT(*) FROM profiles WHERE user_id=%s AND campaign=%s AND status LIKE 'skipped%'", (user_id, campaign))
                row = cur.fetchone(); skipped = row[0] if row else 0

                pending = max(0, total - success - failed - skipped)

                cur.execute("SELECT username, error FROM profiles WHERE user_id=%s AND campaign=%s AND status='failed'", (user_id, campaign))
                failed_list = [{"username": u, "error": e} for u, e in cur.fetchall()]

            return {
                "total": total,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "pending": pending,
                "failed_profiles": failed_list,
            }
        finally:
            self.pool.putconn(conn)

store = ResultStore()

