from network_proxy.db.models import Base
from network_proxy.db.session import get_engine


def init_database() -> None:
    Base.metadata.create_all(bind=get_engine())
