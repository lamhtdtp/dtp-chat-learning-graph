from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # VNGCloud AI Platform (MaaS) — KHÔNG phải Google AI trực tiếp. Chat/vision
    # gọi qua Anthropic SDK, embedding qua OpenAI SDK, cùng base_url/key (xem
    # app/llm/gateway.py và .env.example để biết lý do 2 giao thức khác nhau).
    ai_platform_api_key: str = ""
    ai_platform_base_url: str = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn"
    # Tên model PHẢI có tiền tố provider ("gemini/...") theo quy ước LiteLLM mà
    # VNGCloud dùng nội bộ — thiếu tiền tố này gây lỗi 404 "model not found"
    # (đã gặp thật, dễ nhầm vì lỗi không nói rõ nguyên nhân là thiếu tiền tố).
    gemini_model_cheap: str = "gemini/gemini-2.5-pro"
    gemini_model_strong: str = "gemini/gemini-2.5-pro"
    embedding_model: str = "gemini/gemini-embedding-001"

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
