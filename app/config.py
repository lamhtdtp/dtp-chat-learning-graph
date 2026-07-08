from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_api_key: str = ""
    gemini_model_cheap: str = "gemini-2.5-flash-lite"
    gemini_model_strong: str = "gemini-2.5-pro"
    embedding_model: str = "gemini-embedding-001"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sgk_toan"

    database_url: str = "postgresql+asyncpg://lamthanh@localhost:5432/chat_learning"
    redis_url: str = "redis://localhost:6379/1"

    jwt_secret: str = ""

    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    cors_origins: str = "http://localhost:5173"


settings = Settings()
