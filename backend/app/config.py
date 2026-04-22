from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "minerva-api"
    database_url: str = Field(
        default="postgresql+asyncpg://minerva:minerva@127.0.0.1:5432/minerva",
        description="Async SQLAlchemy URL (asyncpg driver).",
    )
    sync_database_url: str = Field(
        default="postgresql+psycopg2://minerva:minerva@127.0.0.1:5432/minerva",
        description="Sync URL for Alembic and scripts (psycopg2).",
    )
    jwt_secret: str = Field(
        default="change_me_dev_only_32_bytes_minimum_please",
    )
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    bcrypt_rounds: int = 12


settings = Settings()
