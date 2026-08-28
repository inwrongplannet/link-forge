from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import urls, redirect, auth, analytics, health
from app.database.bootstrap import initialize_database
from app.middleware.error_handlers import register_exception_handlers
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger("linkforge")

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Link Forge", version="0.1.0", lifespan=lifespan)
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    app.include_router(health.router)
    app.include_router(urls.router)
    app.include_router(redirect.router)
    app.include_router(auth.router)
    app.include_router(analytics.router)
    register_exception_handlers(app)

    return app



app = create_app()

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )
