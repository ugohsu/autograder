import os
import sqlite3

from flask import g

OPTION_SYMBOLS = ["①", "②", "③", "④", "⑤"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "autograder.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# schema.sql の CREATE TABLE IF NOT EXISTS だけでは既存DBに新しい列は追加されないため、
# 後から列を足したときはここに (table, column, coltype) を追加する。
_COLUMN_MIGRATIONS = [
    ("batches", "note", "TEXT"),
    ("answers", "raw_marked_options", "TEXT"),
    ("answers", "is_ambiguous", "INTEGER NOT NULL DEFAULT 0"),
    ("students", "canonical_image", "BLOB"),
    ("answers", "reviewed", "INTEGER NOT NULL DEFAULT 0"),
]


def _migrate_columns(conn):
    added = set()
    for table, column, coltype in _COLUMN_MIGRATIONS:
        existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            added.add((table, column))
    return added


def get_db():
    if "db" not in g:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        added = _migrate_columns(conn)
        if ("answers", "reviewed") in added:
            # reviewed 列を新規追加した既存DBでは、is_ambiguous な行のうち option が
            # 既に入っているもの（＝過去に採点者が手動で選び直し済み）だけ reviewed=1 に
            # 遡って補完する。option が NULL のままの行は「未確認」と「確認の結果、無回答/
            # 無効と判断した」を区別できないため、安全側に倒して未確認のままにする。
            conn.execute(
                "UPDATE answers SET reviewed = 1 "
                "WHERE is_ambiguous = 1 AND option IS NOT NULL"
            )
        conn.commit()
        g.db = conn
    return g.db


def close_db(e=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
