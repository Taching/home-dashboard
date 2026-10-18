"""One-time Garmin Connect login (handles MFA). Run inside the backend container:

    docker exec -it chili-dashboard-backend-1 python -m app.jobs.garmin_login

Tokens are saved to GARMIN_TOKEN_DIR (/data/garminconnect) and refreshed by the
background sync afterwards, so the password does not need to stay in .env.
"""
from __future__ import annotations

import getpass
from datetime import date
from pathlib import Path

from app.core.settings import settings


def main() -> None:
    from garminconnect import Garmin

    email = settings.garmin_email or input("Garmin email: ").strip()
    password = settings.garmin_password or getpass.getpass("Garmin password: ")
    token_dir = Path(settings.garmin_token_dir)
    token_dir.mkdir(parents=True, exist_ok=True)
    client = Garmin(email, password, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
    client.login(tokenstore=str(token_dir))
    client.client.dump(str(token_dir))
    summary = client.get_user_summary(date.today().isoformat())
    print(f"Logged in as {client.full_name or client.display_name}. Tokens saved to {token_dir}.")
    print(f"Today so far: {summary.get('totalSteps') or 0} steps.")


if __name__ == "__main__":
    main()
