import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user = os.getenv("MYSQL_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD", "")
    mysql_db = os.getenv("MYSQL_DB", "music_app")

    fastapi_host = os.getenv("FASTAPI_HOST", "127.0.0.1")
    fastapi_port = int(os.getenv("FASTAPI_PORT", "8000"))
    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "super-secret-key-12345")
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")


settings = Settings()
