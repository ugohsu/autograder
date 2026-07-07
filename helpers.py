import os
import sqlite3

from flask import g

OPTION_SYMBOLS = ["①", "②", "③", "④", "⑤"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "autograder.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def _migrate(conn):
    """schema.sql の CREATE TABLE IF NOT EXISTS では既存DBに新規カラムが
    追加されないため、起動時にカラム差分だけ ALTER TABLE で埋める。"""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(batches)")}
    if "active_question_count" not in cols:
        conn.execute("ALTER TABLE batches ADD COLUMN active_question_count INTEGER")


def get_db():
    if "db" not in g:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            conn.executescript(f.read())
        _migrate(conn)
        conn.commit()
        g.db = conn
    return g.db


def close_db(e=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()
