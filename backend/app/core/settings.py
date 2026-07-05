from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Chili Home Dashboard"
    database_url: str = "sqlite:////data/chili.db"
    timezone: str = "Asia/Tokyo"
    weather_latitude: float | None = 35.6581
    weather_longitude: float | None = 139.7514
    weather_location_name: str = "Minato, Tokyo"
    sensor_poll_interval_seconds: int = 300
    sensor_enabled: bool = True
    sensor_i2c_address: int = 0x44
    broadlink_host: str | None = None
    broadlink_mac: str | None = None
    broadlink_device_type: int | None = None
    broadlink_codes_path: str = "/data/learned-codes/lights.json"
    screen_on_hour: int = 8
    screen_off_hour: int = 22
    display_schedule_enabled: bool = True
    display_power_script: str = "/deploy/display-power.sh"
    display_wayland_display: str = "wayland-0"
    display_xdg_runtime_dir: str = "/run/user/1000"
    display_hdmi_output: str | None = None
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
    notion_due_property: str = "Due Date"
    notion_done_property: str = "Done"
    notion_status_property: str = "Status"
    notion_type_property: str = "Type"
    notion_done_statuses: str = "Done,Complete,Completed"
    openclaw_gateway_ws_url: str | None = None
    openclaw_gateway_token: str | None = None
    openclaw_session_key: str = "agent:main:main"
    openclaw_prefer_telegram_session: bool = True
    switchbot_token: str | None = None
    switchbot_secret: str | None = None
    switchbot_plug_device_id: str | None = None
    water_pump_duration_seconds: int = 20
    dashboard_automation_token: str | None = None
    walkingpad_ble_name: str | None = None
    walkingpad_bridge_token: str | None = None
    walkingpad_goal_minutes: int = 45
    walkingpad_goal_distance_km: float = 3.0
    walkingpad_reminder_start_hour: int = 10
    walkingpad_reminder_end_hour: int = 20
    walkingpad_min_gap_before_meeting_min: int = 60
    walkingpad_min_session_minutes: int = 15


settings = Settings()
