"""Settings loaded from environment / .env. Every API credential lives here."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    wzm_env: str = "dev"
    wzm_database_url: str = "postgresql://wzm:wzm@localhost:5432/wzm"
    wzm_data_dir: Path = Path("./data")
    wzm_streams_file: Path = Path("./config/datastreams.yaml")

    # Work zone events
    wzdx_feed_url: str = ""
    wzdx_api_key: str = ""
    permits_api_url: str = ""
    permits_api_key: str = ""

    # Speeds
    npmrds_username: str = ""
    npmrds_password: str = ""
    inrix_app_id: str = ""
    inrix_hash_token: str = ""
    here_api_key: str = ""

    # Volumes
    detectors_api_url: str = ""
    detectors_api_key: str = ""

    # Context
    crashes_db_url: str = ""
    noaa_api_token: str = ""
    noaa_user_agent: str = ""
    events_api_url: str = ""
    incidents_api_url: str = ""
    incidents_api_key: str = ""

    # Outputs
    dms_api_url: str = ""
    dms_api_key: str = ""
    alert_511_url: str = ""
    smtp_url: str = ""
    alert_email_to: str = ""

    def get(self, env_name: str) -> str:
        return str(getattr(self, env_name.lower(), "") or "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
