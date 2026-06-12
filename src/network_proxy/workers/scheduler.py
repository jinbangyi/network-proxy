from apscheduler.schedulers.background import BackgroundScheduler

from network_proxy.db.session import SessionLocal
from network_proxy.services.health import HealthService
from network_proxy.settings import Settings


def build_scheduler(settings: Settings) -> BackgroundScheduler | None:
    if not settings.health_check_enabled:
        return None

    scheduler = BackgroundScheduler()

    def _run_health_check() -> None:
        with SessionLocal() as session:
            HealthService(session, settings).run_once()

    scheduler.add_job(
        _run_health_check,
        "interval",
        seconds=settings.health_check_interval_seconds,
        id="health-check",
        replace_existing=True,
    )
    return scheduler
