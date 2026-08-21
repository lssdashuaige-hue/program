from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.data_control import router as data_control_router
from app.api.evals import router as evals_router
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(data_control_router)
app.include_router(evals_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    if request.url.path.startswith("/internal/evals"):
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid synthetic evaluation request."},
        )
    return await request_validation_exception_handler(request, exc)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "PAS backend running", "environment": settings.app_env}
