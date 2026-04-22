from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "minerva-api"
    database_url: str = Field(
        default="postgresql+asyncpg://minerva:minerva@127.0.0.1:5432/minerva",
        description="Async SQLAlchemy URL (asyncpg driver).",
    )


settings = Settings()
