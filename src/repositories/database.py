import sqlite3
from contextlib import contextmanager
from threading import RLock


class Database:
    def __init__(self, path=":memory:"):
        self.lock = RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, document TEXT NOT NULL UNIQUE,
                balance_cents INTEGER NOT NULL CHECK(balance_cents >= 0));
            CREATE TABLE IF NOT EXISTS transfers (
                id TEXT PRIMARY KEY, idem_key TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL REFERENCES accounts(id),
                target TEXT NOT NULL REFERENCES accounts(id),
                amount INTEGER NOT NULL CHECK(amount > 0), created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
                transfer_id TEXT REFERENCES transfers(id), type TEXT NOT NULL,
                amount_cents INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
                transfer_id TEXT PRIMARY KEY REFERENCES transfers(id),
                payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0);
        """)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def close(self):
        self.connection.close()
