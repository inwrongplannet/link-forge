import logging

from alembic import command
from alembic.config import Config

from app.database.config import settings

logger = logging.getLogger(__name__)

_ALEMBIC_CFG = Config("alembic.ini")
_ALEMBIC_CFG.set_main_option("sqlalchemy.url", settings.database_url)


def initialize_database() -> None:
    """Run Alembic migrations against the database.

    Called once at application startup (lifespan).  Using Alembic instead of
    ``Base.metadata.create_all`` means DDL changes are version-controlled and
    safe to run concurrently across workers.
    """
    try:
        logger.info("Running Alembic migrations (alembic upgrade head)")
        command.upgrade(_ALEMBIC_CFG, "head")
        logger.info("Alembic migrations completed successfully")
    except Exception:
        logger.exception("Alembic migration failed")
        raise
