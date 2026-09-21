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
    _ensure_column("calendar_bridge_events", "calendar_title", "VARCHAR(255)")
    _ensure_column("calendar_bridge_events", "managed_session_id", "VARCHAR(36)")
    _ensure_column("training_logs", "exercises", "TEXT")
    _ensure_column("training_exercises", "done", "BOOLEAN NOT NULL DEFAULT 0")
    _ensure_column("daily_wellbeing_checkins", "gym", "BOOLEAN")
    _ensure_column("daily_wellbeing_checkins", "jiujitsu", "BOOLEAN")
    _ensure_column("daily_wellbeing_checkins", "weight_kg", "FLOAT")
    for name, sql_type in {
        "sleep_hours": "FLOAT",
        "sleep_quality": "INTEGER",
        "fatigue": "INTEGER",
        "soreness": "INTEGER",
        "grip_fatigue": "INTEGER",
        "pain": "BOOLEAN",
        "pain_notes": "VARCHAR(500)",
        "readiness": "INTEGER",
        "fatigue_state": "VARCHAR(32)",
        "daily_notes": "TEXT",
        "advice": "TEXT",
        "chili_reply": "TEXT",
        "chili_delivery": "VARCHAR(32)",
    }.items():
        _ensure_column("daily_wellbeing_checkins", name, sql_type)
    _ensure_column("training_planner_settings", "declined_bjj_dates", "JSON")
    _ensure_column("training_planner_settings", "last_adjustment", "JSON")
    _ensure_column("training_planner_settings", "class_template", "JSON")
    _ensure_column("training_planner_settings", "gym_id", "VARCHAR(40)")
    _ensure_column("training_sessions", "miss_reason", "VARCHAR(32)")
    _ensure_column("weekly_reviews", "coach_review", "TEXT")


def _ensure_column(table: str, name: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table)}
    if name in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
