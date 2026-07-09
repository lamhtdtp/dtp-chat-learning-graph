from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # VNGCloud AI Platform (MaaS) — KHÔNG phải Google AI trực tiếp. Mỗi model
    # gọi qua 1 giao thức khác nhau (xem app/llm/gateway._PROTOCOL_BY_MODEL,
    # đã verify từng model qua API thật) dù dùng chung base_url/key.
    ai_platform_api_key: str = ""
    ai_platform_base_url: str = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn"
    # Tên model PHẢI có tiền tố provider ("gemini/...") theo quy ước LiteLLM mà
    # VNGCloud dùng nội bộ — thiếu tiền tố này gây lỗi 404 "model not found"
    # (đã gặp thật, dễ nhầm vì lỗi không nói rõ nguyên nhân là thiếu tiền tố).
    gemini_model_cheap: str = "gemini/gemini-3.1-flash-lite"
    gemini_model_strong: str = "gemini/gemini-3.1-pro-preview"
    embedding_model: str = "openai/text-embedding-3-large"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sgk_toan"

    database_url: str = "postgresql+asyncpg://lamthanh@localhost:5432/chat_learning"
    redis_url: str = "redis://localhost:6380/0"

    jwt_secret: str = ""

    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080"


settings = Settings()
