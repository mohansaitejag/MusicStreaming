import uvicorn
from backend.core.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.fastapi_host,
        port=settings.fastapi_port,
        reload=True,
    )
