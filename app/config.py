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
    # Tài khoản VNGCloud hiện CHỈ có google/gemma-4-31b-it (xem
    # `python -m app.llm.tu_kiem`). Hai tầng trỏ cùng model: không còn
    # model reasoning riêng nên "strong" chỉ khác ở max_tokens.
    gemini_model_cheap: str = "google/gemma-4-31b-it"
    gemini_model_strong: str = "google/gemma-4-31b-it"
    # baai/bge-m3 — dense 1024 chiều (KHÁC 3072 của text-embedding-3-large, vốn
    # đã bị provider bỏ: 404 "model is not found"). Đổi model embedding thì PHẢI
    # nạp lại toàn bộ Qdrant, và vì lệch chiều nên còn phải tạo lại collection —
    # xem app/ingestion/qdrant_store.py.
    embedding_model: str = "baai/bge-m3"
    image_model: str = "openai/gpt-image-1"  # sinh ảnh nền cảnh video (đã verify)

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sgk_toan"

    # DTP Testbank — kho câu hỏi ôn luyện (PUBLIC) cho đề cuối kỳ. Gọi máy chủ
    # sang máy chủ bằng tài khoản dịch vụ vai DOI_TAC_ON_LUYEN (app/integrations/
    # testbank). Ba gốc RIÊNG vì prod là một tên miền + tiền tố, máy dev là ba cổng:
    #   prod: https://testbank.dtpsoft.vn/api/identity | /api/content | /api/exam
    #   dev : http://127.0.0.1:8002 | :8001 | :8003
    # Thiếu bất kỳ giá trị nào -> đề cuối kỳ báo "chưa kết nối", không 500.
    # Mật khẩu chỉ để ở kho bí mật của máy chủ, KHÔNG commit.
    testbank_identity_url: str = ""
    testbank_content_url: str = ""
    testbank_exam_url: str = ""
    testbank_email: str = ""
    testbank_password: str = ""
    # Số lần rút đề cuối kỳ / học sinh / ngày (0 = không giới hạn; admin miễn).
    # Mỗi lần rút là 2 lượt gọi testbank + tới 12 lượt gọi model sinh lý do ở lần
    # đầu, và testbank xin giữ dưới ~10 lời gọi/giây.
    de_cuoi_ky_daily_limit: int = 10
    # Số lượt rút "Luyện thêm từ kho đề" / học sinh / ngày (US-25 Q6; 0 = không giới
    # hạn; admin miễn). Riêng với đề cuối kỳ. Mỗi lượt rút là 2 lượt gọi testbank
    # và tới 4 lượt gọi model sinh lý do (câu đã có lý do thì 0).
    luyen_them_daily_limit: int = 20
    # Số đề giao (lần xem trước rút được >= 1 câu, kể cả bản bị huỷ) / giáo viên / ngày
    # giờ Việt Nam (US-26 Q11; 0 = không giới hạn; admin miễn). Mỗi lần là 2 lượt gọi
    # testbank + tới 12 lượt gọi model sinh lý do.
    de_giao_daily_limit: int = 20

    database_url: str = "postgresql+asyncpg://lamthanh@localhost:5432/chat_learning"
    redis_url: str = "redis://localhost:6380/0"

    jwt_secret: str = ""

    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080"

    # Chống lạm dụng / kiểm soát chi phí LLM (mỗi lượt chat tốn tiền model).
    chat_daily_limit: int = 20   # số lượt chat / user / ngày (0 = không giới hạn); admin miễn
    # Độ dài tối đa 1 câu hỏi (chặn input rác/quá dài gây treo + tốn token). 500 chứ
    # không phải 200: đề Toán dán từ sách ("Cho tam giác ABC có AB = 3cm…, tính…")
    # vượt 200 rất dễ, mà 500 ký tự ≈ 150 token — không đáng kể về chi phí.
    # Frontend đọc lại con số này qua GET /tutor/limits, không hardcode.
    chat_max_chars: int = 500
    # Tắt trợ lý AI có thông báo tử tế (đổi bằng env, KHÔNG cần deploy lại code).
    # Dùng khi provider mất model / hết quota / đang bảo trì: học sinh thấy lời
    # nhắn thay vì gõ câu hỏi rồi nhận lỗi và mất lượt.
    tro_ly_bao_tri: bool = False
    tro_ly_bao_tri_nhan: str = (
        "Trợ lý AI đang bảo trì nên tạm thời chưa trả lời được. "
        "Em cứ đọc bài và làm bài kiểm tra nhanh nhé, mai quay lại hỏi mình!"
    )
    # Độ dài tối đa ô "Tư liệu nguồn cho AI" trong CMS. Rộng hơn ô chat nhiều vì
    # đây là chỗ dán nguyên trích đoạn SGK, nhưng vẫn phải có trần: chuỗi này đi
    # THẲNG vào prompt soạn bài nên dán cả chương vào là phình token + dễ tràn
    # cửa sổ ngữ cảnh. Frontend đọc lại qua GET /cms/limits.
    cms_nguon_max_chars: int = 5000

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
