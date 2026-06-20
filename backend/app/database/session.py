from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialise_database() -> None:
    # Importing models registers all mapped tables before create_all runs.
    from app.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # `create_all` does not alter existing SQLite tables. Keep this small,
    # idempotent migration here until the project adopts a versioned migration tool.
    columns = {column["name"] for column in inspect(engine).get_columns("calendar_bridge_events")}
    if "is_all_day" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE calendar_bridge_events ADD COLUMN is_all_day BOOLEAN NOT NULL DEFAULT 0")
            )
