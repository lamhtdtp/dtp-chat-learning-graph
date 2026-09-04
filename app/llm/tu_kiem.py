"""Tự kiểm kết nối LLM — chạy khi API trả 500 ở các đường gọi AI.

    python -m app.llm.tu_kiem

In ra bốn thứ, theo đúng thứ tự cần loại trừ:
  1. base URL + có key hay không
  2. GET /v1/models — key có hợp lệ không, và tài khoản CÓ MODEL NÀO không
  3. model đang cấu hình có nằm trong danh sách đó không
  4. gọi thật 1 token mỗi tầng

Vì sao cần: model không tồn tại thì provider trả 404, mà 404 KHÔNG phải lỗi tạm
thời nên trước đây nó xuyên qua gateway thành HTTP 500 trơ trọi — log chỉ có
traceback openai.NotFoundError, không nói model nào sai hay key thiếu quyền.
"""
import asyncio

import httpx

from app.config import settings
from app.llm import gateway
from app.llm.gateway import LLMUnavailable


async def _danh_sach_model() -> list[str] | None:
    base = settings.ai_platform_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{base}/v1/models",
                        headers={"Authorization": f"Bearer {settings.ai_platform_api_key}"})
        print(f"2. GET /v1/models -> {r.status_code}")
        if r.status_code == 401:
            print("   ✗ Key SAI hoặc hết hạn (401). Sửa AI_PLATFORM_API_KEY.")
            return None
        if r.status_code != 200:
            print(f"   ✗ {r.text[:200]}")
            return None
        ds = [x.get("id", "") for x in (r.json().get("data") or []) if isinstance(x, dict)]
        if not ds:
            print("   ✗ Key HỢP LỆ nhưng tài khoản KHÔNG CÓ MODEL NÀO "
                  "(gói/quota/deployment hết hoặc project chưa được gán model).")
            print("     -> Mọi lệnh gọi sẽ 404 'The requested model is not found'.")
            print("     -> Xử ở Console VNGCloud, không sửa được bằng code.")
            return []
        print(f"   ✓ {len(ds)} model: " + ", ".join(ds[:12]))
        return ds


async def main() -> None:
    key = settings.ai_platform_api_key
    print(f"1. base = {settings.ai_platform_base_url}")
    print(f"   key  = {'có (' + str(len(key)) + ' ký tự)' if key else '✗ TRỐNG'}")
    if not key:
        print("   -> Đặt AI_PLATFORM_API_KEY trong .env rồi `up -d api worker`.")
        return

    ds = await _danh_sach_model()

    dang_dung = {"cheap (qa, OCR, gợi ý media)": settings.gemini_model_cheap,
                 "strong (soạn bài, sinh đề)": settings.gemini_model_strong,
                 "embedding (tra SGK)": settings.embedding_model}
    print("\n3. Model đang cấu hình:")
    for nhan, m in dang_dung.items():
        if ds is None:
            trang_thai = "?"
        elif not ds:
            trang_thai = "✗ (không có model nào)"
        else:
            trang_thai = "✓ có trong danh sách" if m in ds else "✗ KHÔNG có trong danh sách"
        print(f"   {nhan:34} {m:42} {trang_thai}")

    print("\n4. Gọi thật 1 token:")
    for task in ("qa", "quiz_gen"):
        try:
            out = await gateway.complete(
                task=task, messages=[{"role": "user", "content": "ping"}], max_tokens=8)
            print(f"   {task:10} ✓ trả lời {out[:40]!r}")
        except LLMUnavailable as e:
            print(f"   {task:10} ✗ tạm thời (429/mất kết nối): {e}")
        except Exception as e:  # noqa: BLE001 — in đúng loại lỗi để lần
            print(f"   {task:10} ✗ {type(e).__name__}: {str(e)[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
