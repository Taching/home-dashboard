"""Idempotently provision the Notion Training Sessions database.

Run from the backend environment and copy the printed assignment into `.env`.
The script deliberately discovers the parent through the already configured Tasks
data source so no workspace or page identifier is hard-coded.
"""

from __future__ import annotations

import httpx

from app.core.settings import settings


API = "https://api.notion.com/v1"
VERSION = "2026-03-11"
DATABASE_TITLE = "Training Sessions"


def _options(names: list[str]) -> dict:
    colors = ["blue", "purple", "green", "orange", "yellow", "red", "gray", "pink"]
    return {"options": [{"name": name, "color": colors[index % len(colors)]} for index, name in enumerate(names)]}


def _schema() -> dict:
    workout_types = [
        "bjj_technical", "bjj_normal", "bjj_hard", "strength_a", "strength_b",
        "zone_2", "grip", "recovery", "rest", "competition",
    ]
    properties = {
        "Name": {"title": {}},
        "Local Session ID": {"rich_text": {}},
        "Date": {"date": {}},
        "Planned Type": {"select": _options(workout_types)},
        "Actual Type": {"select": _options(workout_types)},
        "Status": {"select": _options(["Planned", "Completed", "Partial", "Skipped", "Recovery", "Competition"])},
        "Competition Phase": {"select": _options([
            "build_october", "taper_october", "competition_october", "recovery_october",
            "build_november", "taper_november", "competition_november", "post_competition",
        ])},
        "Pain": {"checkbox": {}},
    }
    for name in (
        "Strength Exercises", "Bike Intervals", "Notes", "Coach Focus",
        "Rescheduled From", "Calendar Event ID",
    ):
        properties[name] = {"rich_text": {}}
    for name in (
        "Duration", "BJJ Rounds", "BJJ Round Length", "BJJ Rest Seconds", "Session RPE",
        "Final Round Quality", "Body Weight", "Sleep Hours", "Sleep Quality", "Fatigue",
        "Soreness", "Grip Fatigue", "Readiness", "Zone 2 Average HR", "Zone 2 Max HR",
        "Zone 2 Distance",
    ):
        properties[name] = {"number": {"format": "number"}}
    return properties


def provision() -> str:
    if not settings.notion_token or not settings.notion_data_source_id:
        raise RuntimeError("NOTION_TOKEN and NOTION_DATA_SOURCE_ID must be configured first.")
    headers = {
        "Authorization": f"Bearer {settings.notion_token}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=20, headers=headers) as client:
        if settings.notion_training_data_source_id:
            configured = client.get(f"{API}/data_sources/{settings.notion_training_data_source_id}")
            if configured.status_code == 200:
                return settings.notion_training_data_source_id
            if configured.status_code != 404:
                configured.raise_for_status()

        source = client.get(f"{API}/data_sources/{settings.notion_data_source_id}")
        source.raise_for_status()
        page_id = source.json().get("database_parent", {}).get("page_id")
        if not page_id:
            raise RuntimeError("The configured Tasks data source does not expose a writable parent page.")

        child_matches: list[str] = []
        cursor: str | None = None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            children = client.get(f"{API}/blocks/{page_id}/children", params=params)
            children.raise_for_status()
            payload = children.json()
            child_matches.extend(
                str(item["id"]) for item in payload.get("results", [])
                if item.get("type") == "child_database"
                and item.get("child_database", {}).get("title") == DATABASE_TITLE
            )
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
        if len(child_matches) == 1:
            return _first_data_source(client, child_matches[0])
        if len(child_matches) > 1:
            raise RuntimeError("Multiple Training Sessions databases exist under the configured parent; set NOTION_TRAINING_DATA_SOURCE_ID explicitly.")

        search = client.post(f"{API}/search", json={"query": DATABASE_TITLE, "page_size": 100})
        search.raise_for_status()
        for item in search.json().get("results", []):
            title = "".join(part.get("plain_text", "") for part in item.get("title", []))
            if item.get("object") == "database" and title == DATABASE_TITLE:
                return _first_data_source(client, str(item["id"]))

        created = client.post(f"{API}/databases", json={
            "parent": {"type": "page_id", "page_id": page_id},
            "title": [{"type": "text", "text": {"content": DATABASE_TITLE}}],
            "description": [{"type": "text", "text": {"content": "Competition plans and actual training, synchronized idempotently by Chili."}}],
            "icon": {"type": "emoji", "emoji": "🥋"},
            "is_inline": False,
            "initial_data_source": {"properties": _schema()},
        })
        created.raise_for_status()
        return _first_data_source(client, str(created.json()["id"]))


def _first_data_source(client: httpx.Client, database_id: str) -> str:
    response = client.get(f"{API}/databases/{database_id}")
    response.raise_for_status()
    sources = response.json().get("data_sources", [])
    if not sources or not sources[0].get("id"):
        raise RuntimeError("Notion database has no initial data source.")
    return str(sources[0]["id"])


if __name__ == "__main__":
    print(f"NOTION_TRAINING_DATA_SOURCE_ID={provision()}")
