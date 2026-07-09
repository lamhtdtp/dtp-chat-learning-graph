"""Eval retrieval: recall@k trên dataset câu hỏi + trang đúng kỳ vọng.

Đây là eval (metric + ngưỡng), KHÁC unit test (nhị phân): đo trên dataset, so
baseline, theo dõi hồi quy (xem testing-tdd-eval Phần D). Ngưỡng gợi ý
recall@5 >= 0.85. Không chặn merge; chạy như CI job riêng / khi đổi model
embedding, ghi rõ model đang dùng để có baseline so sánh.

    python -m evals.run_retrieval_eval
"""

import asyncio
import json
from pathlib import Path

from app.config import settings
from app.retrieval import retriever

DATASET = Path(__file__).parent / "dataset_retrieval.jsonl"
TOP_K = 5
NGUONG = 0.85


def _load() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


async def danh_gia(top_k: int = TOP_K) -> dict:
    items = _load()
    hits = 0
    chi_tiet = []
    for item in items:
        results = await retriever.retrieve(item["cau_hoi"], mon="toan", khoi="lop_6", top_k=top_k)
        trang_tra_ve = [r.page_no for r in results]
        hit = any(p in trang_tra_ve for p in item["trang_dung"])
        hits += hit
        chi_tiet.append({"cau_hoi": item["cau_hoi"], "ky_vong": item["trang_dung"],
                         "tra_ve": trang_tra_ve, "hit": hit})
    recall = hits / len(items) if items else 0.0
    return {"recall_at_k": recall, "k": top_k, "so_cau": len(items), "chi_tiet": chi_tiet}


async def _main() -> None:
    print(f"Embedding model: {settings.embedding_model}")
    kq = await danh_gia()
    for d in kq["chi_tiet"]:
        mark = "✓" if d["hit"] else "✗"
        print(f"  {mark} {d['cau_hoi'][:50]:52} ky_vong={d['ky_vong']} tra_ve={d['tra_ve']}")
    print(f"\nrecall@{kq['k']} = {kq['recall_at_k']:.3f} (ngưỡng {NGUONG}) trên {kq['so_cau']} câu")
    print("KẾT QUẢ:", "ĐẠT" if kq["recall_at_k"] >= NGUONG else "DƯỚI NGƯỠNG")


if __name__ == "__main__":
    asyncio.run(_main())
