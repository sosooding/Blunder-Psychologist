from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, loaded from environment / .env.

    Field names map case-insensitively to env vars (database_url <- DATABASE_URL).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://blunder:blunder@localhost:5432/blunder"
    llm_provider: str = "gemini"
    lichess_token: str | None = None
    worker_poll_interval: float = 1.0
    worker_max_attempts: int = 3


settings = Settings()
