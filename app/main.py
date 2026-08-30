import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import analytics, auth, health, redirect, urls
from app.cache.flush_worker import run_flush_worker
from app.database.bootstrap import initialize_database
from app.middleware.error_handlers import register_exception_handlers
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger("linkforge")

_flush_stop_event = threading.Event()
_flush_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _flush_thread
    initialize_database()

    _flush_thread = threading.Thread(
        target=run_flush_worker,
        kwargs={"stop_event": _flush_stop_event},
        daemon=True,
        name="click-flush-worker",
    )
    _flush_thread.start()
    logger.info("Click flush worker thread started")

    yield

    _flush_stop_event.set()
    if _flush_thread:
        _flush_thread.join(timeout=15)
    logger.info("Click flush worker thread stopped")


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
