from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes.music import router as music_router
from backend.api.routes.auth import router as auth_router
from backend.db.connection import test_connection

app = FastAPI(title="Music Streaming Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(music_router)


@app.on_event("startup")
def verify_database_connection():
    try:
        db_info = test_connection()
        print(
            f"[DB] Startup check passed for database='{db_info['database']}' on {db_info['host']}:{db_info['port']}"
        )
    except Exception as exc:
        print(f"[DB] Startup check failed: {exc}")


@app.get("/health")
def health():
    return {"status": "ok"}
