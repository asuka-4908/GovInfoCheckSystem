import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE = DATA_DIR / "app.db"

def get_connection():
    conn = sqlite3.connect(str(DATABASE))
    conn.row_factory = sqlite3.Row
    return conn

def query_all(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or [])
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def query_one(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or [])
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def execute_update(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or [])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
