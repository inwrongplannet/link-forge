import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import analytics, auth, health, redirect, urls
from app.cache.flush_worker import run_flush_worker_async
from app.database.bootstrap import initialize_database
from app.middleware.error_handlers import register_exception_handlers
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger("linkforge")

_flush_stop_event: asyncio.Event | None = None
_flush_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _flush_stop_event, _flush_task

    initialize_database()

    _flush_stop_event = asyncio.Event()
    _flush_task = asyncio.create_task(
        run_flush_worker_async(
            stop_event=_flush_stop_event,
        ),
        name="click-flush-worker",
    )
    logger.info("Click flush worker task started")

    yield

    if _flush_stop_event:
        _flush_stop_event.set()
    if _flush_task:
        try:
            await asyncio.wait_for(_flush_task, timeout=15)
        except asyncio.TimeoutError:
            _flush_task.cancel()
    logger.info("Click flush worker task stopped")


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
