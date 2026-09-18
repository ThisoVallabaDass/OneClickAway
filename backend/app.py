"""Application composition and lifecycle for OneClick-Away."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from . import config
from .job_store import JobStore
from .logging_config import configure_logging
from .middleware import BrowserBoundary, RequestLimit
from .routes import router
from .worker import Worker


def create_app(store=None, start_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        worker = Worker(app.state.store) if start_worker else None
        if worker:
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="OneClick-Away", version="9.0.0", lifespan=lifespan)
    app.state.store = store or JobStore(
        config.JOBS_DB, config.RETENTION_SECONDS, config.MAX_PENDING_JOBS
    )
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=config.ROOT / "static"), name="static")
    app.add_middleware(RequestLimit)
    app.add_middleware(
        BrowserBoundary, origins=config.ALLOWED_ORIGINS, secure=config.SECURE_COOKIES
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)
    return app


app = create_app()
