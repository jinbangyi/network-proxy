from contextlib import asynccontextmanager

from fastapi import FastAPI

from network_proxy.api.admin import router as admin_router
from network_proxy.api.node import router as node_router
from network_proxy.api.subscribe import router as subscribe_router
from network_proxy.db.migrations import init_database
from network_proxy.db.session import SessionLocal
from network_proxy.services.relay import RelayService
from network_proxy.settings import get_settings
from network_proxy.workers.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    settings = get_settings()
    with SessionLocal() as session:
        RelayService(session, settings).sync_manager_runtime_config()
    scheduler = build_scheduler(settings)
    if scheduler is not None:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=settings.app_description,
        lifespan=lifespan,
    )
    app.include_router(subscribe_router)
    app.include_router(node_router)
    app.include_router(admin_router)
    return app
