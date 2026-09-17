"""
SQLite接続マネージャー (WALモード対応)
"""
import os
import sqlite3
from typing import Optional
from src.database.schema import CREATE_TABLES_SQL

class DatabaseManager:
    def __init__(self, db_path: str = "user_data/curriculum_v2.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """WALモードのSQLite接続を取得"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # WALモード有効化で同時読み出しと高速書き込みを実現
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_db(self):
        """テーブル初期化"""
        with self.get_connection() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            conn.commit()
