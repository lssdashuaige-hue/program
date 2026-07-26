from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title="PAS API",
    description="Backend for the Psychological AI System alpha.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "PAS backend running", "environment": settings.app_env}
