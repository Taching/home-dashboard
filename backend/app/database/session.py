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
    _ensure_column("calendar_bridge_events", "is_all_day", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("training_logs", "exercises", "TEXT")


def _ensure_column(table: str, name: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table)}
    if name in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
