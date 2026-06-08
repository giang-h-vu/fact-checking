from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth as auth_handler
from app.api import history as history_handler
from app.api import verify as verify_handler
from app.platform.config import get_settings

# TODO: Set this only in development, or use a more sophisticated logging config
logging.basicConfig(level=logging.INFO)



# Initializing database at app startup.
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.platform.db.session import init_db

    await init_db()
    yield

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Fact Checking API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    # Holds Authlib's OAuth state/nonce between the login redirect and the callback.
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.include_router(auth_handler.router)
    app.include_router(verify_handler.router)
    app.include_router(history_handler.router)
    return app


app = create_app()

@app.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})