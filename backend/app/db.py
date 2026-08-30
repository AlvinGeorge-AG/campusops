import os
from contextlib import contextmanager

from .config import DB_PATH

def placeholder() -> str:
    return "?"

def _sqlite_conn():
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    return conn

@contextmanager
def get_db():
    conn = _sqlite_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    from . import state as _s
    conn = _s.get_conn()
    try:
        conn.close()
    except:
        pass

# Backwards compat for old imports
def is_postgres() -> bool:
    return False
