from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chili Home Dashboard"
    database_url: str = "sqlite:////data/chili.db"
    timezone: str = "Asia/Tokyo"
    sensor_poll_interval_seconds: int = 300
    sensor_enabled: bool = True
    sensor_i2c_address: int = 0x44
    screen_on_hour: int = 10
    screen_off_hour: int = 19
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    spotify_redirect_uri: str = "http://127.0.0.1:8080/api/v1/spotify/callback"
    apple_calendar_bridge_token: str | None = None
    openclaw_gateway_ws_url: str | None = None
    openclaw_gateway_token: str | None = None
    openclaw_session_key: str = "agent:main:main"


settings = Settings()
