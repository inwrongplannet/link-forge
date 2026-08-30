from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://abhishek:user1234@127.0.0.1:5432/link_forge"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 60
    base_url: str = "http://localhost:8000"
    jwt_secret_key: str = "supersecretkey_please_change_in_production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Connection pool settings (per worker)
    pool_size: int = 20
    max_overflow: int = 20
    pool_timeout: int = 5
    pool_recycle: int = 1800

    # Concurrency limiter (per worker)
    max_concurrent_requests: int = 40
    concurrency_timeout: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
DATABASE_URL = settings.database_url

