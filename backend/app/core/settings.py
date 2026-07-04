from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chili Home Dashboard"
    database_url: str = "sqlite:////data/chili.db"
    timezone: str = "Asia/Tokyo"
    sensor_poll_interval_seconds: int = 300
    sensor_enabled: bool = True
    sensor_i2c_address: int = 0x44
    broadlink_host: str | None = None
    broadlink_mac: str | None = None
    broadlink_device_type: int | None = None
    broadlink_codes_path: str = "/data/learned-codes/lights.json"
    screen_on_hour: int = 10
    screen_off_hour: int = 19
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    spotify_redirect_uri: str = "http://127.0.0.1:8080/api/v1/spotify/callback"
    openai_api_key: str | None = None
    voice_command_model: str = "gpt-5-mini"
    pi_volume_card: int = 0
    pi_volume_control: str = "PCM"
    pi_volume_step_percent: int = 10
    apple_calendar_bridge_token: str | None = None
    notion_token: str | None = None
    notion_data_source_id: str | None = None
    notion_database_id: str | None = None
    notion_title_property: str = "Name"
    notion_due_property: str = "Due"
    notion_done_property: str = "Done"
    notion_status_property: str = "Status"
    notion_done_statuses: str = "Done,Complete,Completed"
    openclaw_gateway_ws_url: str | None = None
    openclaw_gateway_token: str | None = None
    openclaw_session_key: str = "agent:main:main"


settings = Settings()
