from mysql.connector import pooling
from backend.core.config import settings

_pool = None


def get_connection():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="music_app_pool",
            pool_size=10,
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_db,
        )
        print(
            f"[DB] Connection pool initialized for {settings.mysql_user}@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_db}"
        )
    return _pool.get_connection()


def test_connection():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DATABASE(), @@hostname, @@port")
        database_name, hostname, port = cur.fetchone()
        print(
            f"[DB] Connection successful. Connected to database='{database_name}' on {hostname}:{port}"
        )
        return {
            "database": database_name,
            "host": hostname,
            "port": port,
        }
    finally:
        cur.close()
        conn.close()
