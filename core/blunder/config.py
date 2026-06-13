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

    # Ingestion / funnel (Phase 3)
    backfill_strategy: str = "stratified"
    backfill_max_games: int = 400
    scan_chunk_size: int = 25
    book_threshold: int = 100  # explorer games-count floor for "in book"
    cheap_delta_threshold: int = 100  # cp loss to flag a candidate in the cheap pass
    deep_nodes: int = 2_000_000
    scan_nodes: int = 100_000
    engine_count: int = 1  # Stockfish processes per analysis batch
    stockfish_path: str = ""  # empty -> engine uses its compiled-in default / $STOCKFISH_PATH


settings = Settings()
