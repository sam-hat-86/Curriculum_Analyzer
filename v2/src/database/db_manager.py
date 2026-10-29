"""
SQLite接続マネージャー (WALモード対応)
"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator
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
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """確実に close する接続コンテキスト (正常終了時は commit、例外時は rollback)"""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def init_db(self):
        """テーブル初期化"""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(CREATE_TABLES_SQL)
            # 既存テーブルへのカラムマイグレーション
            for table in ["targets", "progress_summary"]:
                try:
                    cursor = conn.cursor()
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [row["name"] for row in cursor.fetchall()]
                    if "progress_delay" not in columns:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN progress_delay TEXT DEFAULT 'OK'")
                except Exception:
                    pass
