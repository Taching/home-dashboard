"""Live Rich terminal UI for the voice pipeline."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from rich.align import Align
from rich.box import HEAVY, ROUNDED
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

STATE_STYLE = {
    "offline": ("dim white", "○"),
    "idle": ("green", "●"),
    "listening": ("yellow bold", "◉"),
    "thinking": ("cyan bold", "◎"),
    "complete": ("bright_green bold", "✓"),
    "error": ("red bold", "✗"),
}

DIRECTION_STYLE = {
    "in": ("bold cyan", "→"),
    "out": ("bold magenta", "←"),
    "info": ("bold yellow", "•"),
}

SERVICE_STYLE = {
    "openai": "green",
    "backend": "blue",
    "voice": "bright_magenta",
}


def backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")


def local_time(iso: str | None, tz: ZoneInfo) -> str:
    if not iso:
        return "—"
    try:
        parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return parsed.astimezone(tz).strftime("%H:%M:%S")
    except ValueError:
        return iso[:8]


def fetch(client: httpx.Client, url: str) -> tuple[dict | None, list[dict], str | None]:
    try:
        status = client.get(f"{url}/api/v1/voice/status").raise_for_status().json()
        events = client.get(f"{url}/api/v1/voice/events", params={"limit": 40}).raise_for_status().json()
        return status, events, None
    except httpx.HTTPError as error:
        return None, [], str(error)


def state_header(status: dict | None, error: str | None) -> RenderableType:
    if error:
        body = Group(
            Text("Could not reach backend", style="red bold"),
            Text(error, style="dim"),
        )
        return Panel(body, title="Voice", border_style="red", box=ROUNDED)

    state = str(status.get("state", "offline"))
    style, glyph = STATE_STYLE.get(state, ("white", "?"))
    title = Text.assemble(
        ("STATE ", "dim"),
        (state.upper(), style),
        ("  ", ""),
        (glyph, style),
    )

    rows: list[RenderableType] = [title]
    if state in {"listening", "thinking"}:
        rows.append(Spinner("dots", text=f" {state}…", style=style))

    transcript = status.get("transcript")
    message = status.get("message")
    if transcript:
        rows.append(Text.assemble(("Transcript  ", "dim cyan"), (transcript, "white")))
    if message:
        rows.append(Text.assemble(("Response    ", "dim green"), (message, "white")))

    updated = status.get("updated_at")
    if updated:
        rows.append(Text(f"Updated {updated}", style="dim"))

    border = "red" if state == "error" else "cyan" if state == "thinking" else "green" if state == "idle" else "yellow"
    return Panel(Group(*rows), title="[bold]Hey Chili[/] voice", border_style=border, box=HEAVY)


def events_table(events: list[dict], tz: ZoneInfo) -> Table:
    table = Table(box=ROUNDED, expand=True, show_header=True, header_style="bold dim", pad_edge=False)
    table.add_column("Time", style="dim", width=10, no_wrap=True)
    table.add_column("", width=2, justify="center")
    table.add_column("Service", width=8, no_wrap=True)
    table.add_column("Detail", ratio=1)

    for event in events[-24:]:
        direction = str(event.get("direction", "info"))
        d_style, arrow = DIRECTION_STYLE.get(direction, ("white", "?"))
        service = str(event.get("service", "?"))
        s_style = SERVICE_STYLE.get(service, "white")
        detail = str(event.get("detail", ""))
        table.add_row(
            local_time(event.get("at"), tz),
            Text(arrow, style=d_style),
            Text(service, style=s_style),
            detail,
        )

    if not events:
        table.add_row("—", "", "", Text("Waiting for voice activity…", style="dim italic"))

    return table


def build_layout(status: dict | None, events: list[dict], error: str | None, url: str, tz: ZoneInfo) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=8),
        Layout(name="feed", ratio=1),
        Layout(name="footer", size=3),
    )
    layout["header"].update(state_header(status, error))
    layout["feed"].update(
        Panel(events_table(events, tz), title="Pipeline", border_style="blue", box=ROUNDED)
    )
    footer = Align.center(
        Text.assemble(
            ("Polling ", "dim"),
            (url, "cyan"),
            ("  ·  Ctrl+C to quit", "dim"),
        ),
        vertical="middle",
    )
    layout["footer"].update(Panel(footer, box=ROUNDED, border_style="dim"))
    return layout


def main() -> None:
    parser = argparse.ArgumentParser(description="Live terminal monitor for the voice pipeline")
    parser.add_argument("--url", default=backend_url(), help="Dashboard backend base URL")
    parser.add_argument("--refresh", type=float, default=0.4, help="Poll interval in seconds")
    parser.add_argument("--timezone", default=os.environ.get("TZ", "Asia/Tokyo"), help="Display timezone")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    tz = ZoneInfo(args.timezone)
    console = Console()

    console.print(
        Panel(
            Align.center(
                Text.assemble(
                    ("🌶️  ", ""),
                    ("Voice Monitor", "bold cyan"),
                    ("\n", ""),
                    (url, "dim"),
                )
            ),
            border_style="cyan",
            box=ROUNDED,
        )
    )

    with httpx.Client(timeout=5) as client, Live(console=console, refresh_per_second=4, screen=True) as live:
        while True:
            status, events, error = fetch(client, url)
            live.update(build_layout(status, events, error, url, tz))
            time.sleep(max(0.15, args.refresh))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        Console().print("\n[dim]Voice monitor stopped.[/]")
        sys.exit(0)
