"""Export persisted voice command logs for offline analysis."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from app.database.session import initialise_database
from app.domain.voice_log import VoiceLogService


def _rows(entries):
    for entry in entries:
        yield {
            "id": entry.id,
            "occurred_at": entry.occurred_at.isoformat(),
            "transcript": entry.transcript,
            "action": entry.action,
            "interpret_source": entry.interpret_source,
            "artist": entry.artist,
            "volume_percent": entry.volume_percent,
            "intent_message": entry.intent_message,
            "status": entry.status,
            "response_message": entry.response_message,
            "audio_seconds": entry.audio_seconds,
            "wake_score": entry.wake_score,
            "failure_stage": entry.failure_stage,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export voice command logs")
    parser.add_argument("--days", type=int, default=30, help="How many days of history to include")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum number of rows")
    parser.add_argument(
        "--format",
        choices=("json", "jsonl", "csv"),
        default="jsonl",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write to this file instead of stdout",
    )
    args = parser.parse_args()

    initialise_database()
    entries = VoiceLogService().recent(days=args.days, limit=args.limit)
    rows = list(_rows(entries))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        destination = args.output.open("w", encoding="utf-8", newline="")
        close = True
    else:
        destination = sys.stdout
        close = False

    try:
        if args.format == "json":
            json.dump(rows, destination, ensure_ascii=False, indent=2)
            destination.write("\n")
        elif args.format == "jsonl":
            for row in rows:
                destination.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            writer = csv.DictWriter(destination, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)
    finally:
        if close:
            destination.close()


if __name__ == "__main__":
    main()
