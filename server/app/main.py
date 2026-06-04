from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.platform.config import get_settings
from app.api import history as history_handler
from app.api import verify as verify_handler


# Initializing database at app startup.


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.platform.db.session import init_db

    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Fact Checking API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(verify_handler.router)
    app.include_router(history_handler.router)
    return app


app = create_app()
