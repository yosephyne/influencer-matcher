"""
SQLite persistence layer for influencer profiles, settings, and collaboration logs.
Handles encrypted storage for API keys using Fernet.
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from cryptography.fernet import Fernet, InvalidToken

APP_ROOT = Path(__file__).parent.absolute()
DB_PATH = APP_ROOT / 'data' / 'influencer_matcher.db'
FERNET_KEY_PATH = APP_ROOT / 'data' / '.fernet_key'


class Database:
    """SQLite persistence for profiles, ratings, settings."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = None
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS influencer_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT,
                instagram_handle TEXT,
                rating_reliability INTEGER DEFAULT 0,
                rating_content_quality INTEGER DEFAULT 0,
                rating_communication INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                ai_summary TEXT DEFAULT '',
                ai_summary_updated_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                is_encrypted INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS collaboration_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                influencer_name TEXT NOT NULL,
                product TEXT NOT NULL,
                campaign_name TEXT DEFAULT '',
                status TEXT DEFAULT 'planned',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

        # Notion integration columns (added incrementally)
        migration_columns = [
            ("influencer_profiles", "notion_page_id", "TEXT DEFAULT ''"),
            ("influencer_profiles", "notion_status", "TEXT DEFAULT ''"),
            ("influencer_profiles", "notion_produkt", "TEXT DEFAULT ''"),
            ("influencer_profiles", "notion_follower", "INTEGER DEFAULT 0"),
            ("influencer_profiles", "notion_synced_at", "TEXT DEFAULT ''"),
            ("influencer_profiles", "profile_photo", "TEXT DEFAULT ''"),
        ]
        for table, col, col_type in migration_columns:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass  # Column already exists

        conn.commit()
        conn.close()

    # --- Encryption ---

    def _get_fernet(self):
        if self._fernet:
            return self._fernet

        if FERNET_KEY_PATH.exists():
            key = FERNET_KEY_PATH.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            FERNET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            FERNET_KEY_PATH.write_text(key)

        self._fernet = Fernet(key.encode())
        return self._fernet

    def _encrypt(self, plaintext):
        return self._get_fernet().encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext):
        try:
            return self._get_fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return None

    # --- Settings CRUD ---

    def get_setting(self, key):
        conn = self._get_connection()
        row = conn.execute("SELECT value, is_encrypted FROM app_settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        if not row:
            return None
        if row['is_encrypted']:
            return self._decrypt(row['value'])
        return row['value']

    def set_setting(self, key, value, encrypt=False):
        stored_value = self._encrypt(value) if encrypt else value
        conn = self._get_connection()
        conn.execute("""
            INSERT INTO app_settings (key, value, is_encrypted, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                is_encrypted = excluded.is_encrypted,
                updated_at = datetime('now')
        """, (key, stored_value, 1 if encrypt else 0))
        conn.commit()
        conn.close()

    def delete_setting(self, key):
        conn = self._get_connection()
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        conn.commit()
        conn.close()

    # --- AI Provider shortcuts ---

    def get_ai_provider(self):
        """Get current AI provider config. Returns dict or None."""
        provider = self.get_setting('ai_provider')
        api_key = self.get_setting('ai_api_key')
        if not provider or not api_key:
            return None
        return {
            'provider': provider,
            'api_key': api_key,
            'model': self.get_setting('ai_model') or '',
        }

    def save_ai_provider(self, provider, api_key, model=''):
        self.set_setting('ai_provider', provider)
        self.set_setting('ai_api_key', api_key, encrypt=True)
        if model:
            self.set_setting('ai_model', model)

    def clear_ai_provider(self):
        for key in ['ai_provider', 'ai_api_key', 'ai_model']:
            self.delete_setting(key)

    # --- Influencer Profiles ---

    def get_profile(self, name):
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM influencer_profiles WHERE name = ?", (name,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def upsert_profile(self, name, **kwargs):
        conn = self._get_connection()
        existing = conn.execute("SELECT id FROM influencer_profiles WHERE name = ?", (name,)).fetchone()

        if existing:
            if kwargs:
                sets = ', '.join(f"{k} = ?" for k in kwargs)
                sets += ", updated_at = datetime('now')"
                values = list(kwargs.values()) + [name]
                conn.execute(f"UPDATE influencer_profiles SET {sets} WHERE name = ?", values)
                conn.commit()
        else:
            kwargs['name'] = name
            if 'display_name' not in kwargs:
                kwargs['display_name'] = name
            cols = ', '.join(kwargs.keys())
            placeholders = ', '.join('?' * len(kwargs))
            conn.execute(f"INSERT INTO influencer_profiles ({cols}) VALUES ({placeholders})",
                         list(kwargs.values()))
            conn.commit()

        row = conn.execute("SELECT * FROM influencer_profiles WHERE name = ?", (name,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_all_profiles(self):
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM influencer_profiles ORDER BY display_name"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_profiles(self, query):
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM influencer_profiles WHERE name LIKE ? OR display_name LIKE ? ORDER BY display_name",
            (f'%{query}%', f'%{query}%')
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- Notion Data ---

    def update_notion_data(self, name, notion_page_id, notion_status='',
                           notion_produkt='', notion_follower=0):
        """Update Notion-specific fields for a profile."""
        conn = self._get_connection()
        conn.execute("""
            UPDATE influencer_profiles
            SET notion_page_id = ?, notion_status = ?, notion_produkt = ?,
                notion_follower = ?, notion_synced_at = datetime('now'),
                updated_at = datetime('now')
            WHERE name = ?
        """, (notion_page_id, notion_status, notion_produkt, notion_follower, name))
        conn.commit()
        conn.close()

    # --- Collaboration Log ---

    def add_collaboration(self, influencer_name, product, **kwargs):
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO collaboration_log (influencer_name, product, campaign_name, status, notes) VALUES (?, ?, ?, ?, ?)",
            (influencer_name, product, kwargs.get('campaign_name', ''),
             kwargs.get('status', 'planned'), kwargs.get('notes', ''))
        )
        conn.commit()
        conn.close()

    def get_collaborations(self, influencer_name):
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM collaboration_log WHERE influencer_name = ? ORDER BY created_at DESC",
            (influencer_name,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
