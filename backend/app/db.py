import os
from contextlib import contextmanager

from .config import DB_PATH, DATABASE_URL

USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.strip())

_pool = None

def _get_pg_pool():
    global _pool
    if _pool is not None:
        return _pool
    try:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=5, timeout=10, open=True, kwargs={"autocommit": True})
        return _pool
    except Exception as e:
        return None

def is_postgres() -> bool:
    return USE_POSTGRES

def placeholder() -> str:
    return "%s" if USE_POSTGRES else "?"

def _pg_conn():
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)
    conn.execute("SET statement_timeout = 10000")
    return conn

def _sqlite_conn():
    import sqlite3
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=10000;")
    return conn

@contextmanager
def get_db():
    if USE_POSTGRES:
        pool = _get_pg_pool()
        if pool:
            conn = pool.getconn()
            try:
                yield conn
                if not getattr(conn, "autocommit", False):
                    conn.commit()
            except Exception:
                try:
                    if not getattr(conn, "autocommit", False):
                        conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    pool.putconn(conn)
                except Exception:
                    pass
        else:
            conn = _pg_conn()
            try:
                yield conn
                if not getattr(conn, "autocommit", False):
                    conn.commit()
            except Exception:
                try:
                    if not getattr(conn, "autocommit", False):
                        conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    else:
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
    # Ensure tables exist for current backend (called via get_conn pattern elsewhere)
    # We delegate to state.get_conn which creates tables; this just tests connectivity
    from . import state as _s
    conn = _s.get_conn()
    try:
        conn.close()
    except:
        pass
