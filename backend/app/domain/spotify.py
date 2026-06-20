import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.settings import settings
from app.database.models import SpotifyDevice, SpotifyToken
from app.database.session import SessionLocal

SpotifyStatus = Literal["not_configured", "ready", "unavailable"]


class SpotifyService:
    authorize_url = "https://accounts.spotify.com/authorize"
    token_url = "https://accounts.spotify.com/api/token"
    playback_url = "https://api.spotify.com/v1/me/player"
    search_url = "https://api.spotify.com/v1/search"

    def __init__(self) -> None:
        self._pending_states: set[str] = set()

    @property
    def configured(self) -> bool:
        return bool(settings.spotify_client_id and settings.spotify_client_secret)

    @property
    def cipher(self) -> Fernet:
        if not settings.spotify_client_secret:
            raise RuntimeError("Spotify is not configured")
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.spotify_client_secret.encode()).digest()
        )
        return Fernet(key)

    def status(self) -> SpotifyStatus:
        if not self.configured or self._load_token() is None:
            return "not_configured"
        return "ready"

    def begin_authorization(self) -> str:
        if not self.configured:
            raise RuntimeError("Add Spotify credentials to .env before connecting.")

        state = secrets.token_urlsafe(32)
        self._pending_states.add(state)
        query = urlencode(
            {
                "client_id": settings.spotify_client_id,
                "response_type": "code",
                "redirect_uri": settings.spotify_redirect_uri,
                "scope": "user-read-playback-state user-modify-playback-state streaming user-read-email user-read-private",
                "state": state,
            }
        )
        return f"{self.authorize_url}?{query}"

    def complete_authorization(self, code: str, state: str) -> None:
        if state not in self._pending_states:
            raise RuntimeError("Spotify authorization session expired. Try connecting again.")
        self._pending_states.remove(state)

        response = httpx.post(
            self.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
            auth=(settings.spotify_client_id, settings.spotify_client_secret),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        refresh_token = payload.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Spotify did not return a refresh token.")
        self._save_tokens(
            access_token=payload["access_token"],
            refresh_token=refresh_token,
            expires_in=int(payload.get("expires_in", 3600)),
        )

    def now_playing(self) -> dict[str, object]:
        if self.status() != "ready":
            return self._empty(self.status())

        try:
            access_token = self._access_token()
            response = httpx.get(
                self.playback_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            if response.status_code == 204:
                return self._empty("ready")
            response.raise_for_status()
            payload = response.json()
            item = payload.get("item") or {}
            artists = ", ".join(artist["name"] for artist in item.get("artists", [])) or None
            images = item.get("album", {}).get("images", [])
            artwork = images[0]["url"] if images else None
            return {
                "status": "ready",
                "synced_at": datetime.now(UTC),
                "track": item.get("name"),
                "artist": artists,
                "artwork_url": artwork,
                "device_name": payload.get("device", {}).get("name"),
                "is_playing": bool(payload.get("is_playing")),
            }
        except Exception:
            return self._empty("unavailable")

    def web_playback_token(self) -> str:
        return self._access_token()

    def transfer_playback(self, device_id: str) -> None:
        response = httpx.put(
            self.playback_url,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            json={"device_ids": [device_id], "play": True},
            timeout=15,
        )
        response.raise_for_status()

    def register_device(self, device_id: str) -> None:
        with SessionLocal.begin() as session:
            exists = session.scalar(select(SpotifyDevice).where(SpotifyDevice.spotify_device_id == device_id))
            if exists is None:
                session.add(SpotifyDevice(spotify_device_id=device_id))

    def play_artist(self, artist_name: str) -> str:
        access_token = self._access_token()
        search = httpx.get(self.search_url, params={"q": artist_name, "type": "artist", "limit": 5}, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        search.raise_for_status()
        artists = search.json().get("artists", {}).get("items", [])
        if not artists:
            raise RuntimeError("No matching Spotify artist found.")
        normalized = artist_name.casefold()
        artist = next((item for item in artists if item["name"].casefold() == normalized), artists[0])
        response = httpx.put(f"{self.playback_url}/play", params={"device_id": self._registered_device()}, headers={"Authorization": f"Bearer {access_token}"}, json={"context_uri": artist["uri"]}, timeout=15)
        response.raise_for_status()
        return artist["name"]

    def change_volume(self, direction: Literal["up", "down"], step: int = 10) -> int:
        access_token = self._access_token()
        state = httpx.get(self.playback_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        state.raise_for_status()
        current = int(state.json().get("device", {}).get("volume_percent", 50))
        target = max(0, min(100, current + (step if direction == "up" else -step)))
        response = httpx.put(f"{self.playback_url}/volume", params={"device_id": self._registered_device(), "volume_percent": target}, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        response.raise_for_status()
        return target

    def _access_token(self) -> str:
        token = self._load_token()
        if token is None:
            raise RuntimeError("Spotify is not connected")
        if token.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC) + timedelta(seconds=60):
            response = httpx.post(
                self.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.cipher.decrypt(token.encrypted_refresh_token.encode()).decode(),
                },
                auth=(settings.spotify_client_id, settings.spotify_client_secret),
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            self._save_tokens(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token") or self.cipher.decrypt(token.encrypted_refresh_token.encode()).decode(),
                expires_in=int(payload.get("expires_in", 3600)),
            )
            token = self._load_token()
            if token is None:
                raise RuntimeError("Spotify token refresh failed")
        return self.cipher.decrypt(token.encrypted_access_token.encode()).decode()

    def _load_token(self) -> SpotifyToken | None:
        with SessionLocal() as session:
            return session.scalar(select(SpotifyToken).where(SpotifyToken.id == 1))

    def _registered_device(self) -> str:
        with SessionLocal() as session:
            device = session.scalar(select(SpotifyDevice).order_by(SpotifyDevice.id.desc()).limit(1))
        if device is None:
            raise RuntimeError("Chili Spotify player is not ready.")
        return device.spotify_device_id

    def _save_tokens(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        with SessionLocal.begin() as session:
            token = session.get(SpotifyToken, 1)
            if token is None:
                token = SpotifyToken(
                    id=1,
                    encrypted_access_token="",
                    encrypted_refresh_token="",
                    expires_at=expires_at,
                )
                session.add(token)
            token.encrypted_access_token = self.cipher.encrypt(access_token.encode()).decode()
            token.encrypted_refresh_token = self.cipher.encrypt(refresh_token.encode()).decode()
            token.expires_at = expires_at

    @staticmethod
    def _empty(status: SpotifyStatus) -> dict[str, object]:
        return {
            "status": status,
            "synced_at": datetime.now(UTC) if status == "ready" else None,
            "track": None,
            "artist": None,
            "artwork_url": None,
            "device_name": None,
            "is_playing": False,
        }
