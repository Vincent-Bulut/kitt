"""Bring the database schema up to date; run before starting the API.

Databases created before Alembic (by Base.metadata.create_all) have the tables
but no alembic_version table: they are stamped at the baseline revision first,
then upgraded like any other database.

    uv run --project backend --env-file backend/.env python -m backend.migrate
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from backend.api.database import engine

BASELINE = "0001"
ALEMBIC_INI = Path(__file__).with_name("alembic.ini")

log = logging.getLogger("backend.migrate")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    config = Config(str(ALEMBIC_INI))

    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "portfolio" in tables:
        log.info("Existing schema without Alembic history: stamping baseline %s", BASELINE)
        command.stamp(config, BASELINE)

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
