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
    image_model: str = "openai/gpt-image-1"  # sinh ảnh nền cảnh video (đã verify)

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sgk_toan"

    # Itest (EPIC-10) — ngân hàng câu hỏi ngoài, truy cập READ-ONLY qua DB nền
    # tảng (schema unit_test/question, subject='MATH', grade_id='G6'; xem repo
    # dtp-chat-learning). Credential CHỈ-ĐỌC riêng, không nằm trong bất kỳ giao
    # dịch ghi nào. Rỗng -> tính năng Itest tắt (suggest chỉ chạy trên mirror đã
    # đồng bộ). URL ảnh câu hỏi = itest_cdn_base + question.image.
    itest_database_url: str = ""
    itest_cdn_base: str = "https://cdn.i-test.vn/prod/"

    database_url: str = "postgresql+asyncpg://lamthanh@localhost:5432/chat_learning"
    redis_url: str = "redis://localhost:6380/0"

    jwt_secret: str = ""

    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080"

    # Chống lạm dụng / kiểm soát chi phí LLM (mỗi lượt chat tốn tiền model).
    chat_daily_limit: int = 20   # số lượt chat / user / ngày (0 = không giới hạn); admin miễn
    chat_max_chars: int = 500    # độ dài tối đa 1 câu hỏi (chặn input rác/quá dài gây treo + tốn token)

    # Video AI ngắn (Epic-09). Media sinh async, không chặn chat.
    # sgk_version nằm trong concept_key: đổi sách -> cache miss, làm mới video.
    sgk_version: str = "cung_kham_pha_2024"
    video_enabled: bool = True
    video_storage_dir: str = "data/videos"  # object storage nội bộ (dev); prod swap S3/MinIO
    # TTS chính: Gemini TTS qua VNGCloud (endpoint /v1/speech/tts, định dạng
    # Gemini native — KHÁC /v1/audio/speech kiểu OpenAI). Giọng tự nhiên, đa ngữ.
    gemini_tts_model: str = "gemini/gemini-2.5-flash-preview-tts"
    video_tts_voice_cloud: str = "Kore"  # giọng prebuilt Gemini (Kore/Aoede/Zephyr/Puck...)
    video_tts_style: str = "Đọc bằng giọng ấm áp, thân thiện, rõ ràng, vừa phải cho học sinh lớp 6"
    video_tts_voice: str = "Linh"  # dự phòng: giọng vi_VN của macOS `say`
    video_tts_rate: int = 165  # từ/phút cho `say` dự phòng
    video_music: bool = False  # nhạc nền nhẹ (mặc định tắt vì giọng cloud đã tự nhiên)
    video_min_seconds: float = 8.0   # nới cho dev; spec đích 30-90s
    video_max_seconds: float = 90.0


settings = Settings()
