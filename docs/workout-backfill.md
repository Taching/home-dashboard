# Workout logging backfill (Milestone 2)

Idempotent migration that maps existing `TrainingSession` / exercise rows into
the M2 rain metadata and `training_session_exercise_logs` tables.

## How to run

```bash
cd backend
python -c "
from app.database.session import SessionLocal, initialise_database
from app.domain.workout_backfill import run_backfill, get_backfill_mapping

initialise_database()
print(get_backfill_mapping())
print(run_backfill(SessionLocal))
"
```

**Never run this against the Pi production database from an agent environment.**
Test against a fixture copy only.

## Mapping

See `get_backfill_mapping()` in `backend/app/domain/workout_backfill.py` for the
field-by-field map and the list of fields that stay null (no historical data).
