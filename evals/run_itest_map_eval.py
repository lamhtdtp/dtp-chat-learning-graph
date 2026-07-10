"""Eval độ chính xác ánh xạ tag Itest -> taxonomy (EPIC-10, US-22 Scenario 4).

Chạy `suggest_mapping` (qua LLM gateway) trên bộ vàng và so topic_id dự đoán với
đáp án người duyệt. Bao gồm cả ca "không thuộc chương trình" (đáp án null) để
đo cả khả năng TỪ CHỐI map sai.

Nguyên tắc gate: nếu độ chính xác DƯỚI ngưỡng, KHÔNG bật auto-map diện rộng —
giữ người duyệt (đã cưỡng chế trong code: map luôn tạo ở trạng thái 'cho_duyet',
xem app/integrations/itest/mapping.py). Eval này chỉ báo cáo để quyết định.

    python -m evals.run_itest_map_eval
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app.integrations.itest.mapping import suggest_mapping
from app.llm.gateway import LLMUnavailable

DATASET = Path(__file__).resolve().parent / "dataset_itest_map.jsonl"
NGUONG = 0.8  # độ chính xác tối thiểu

# Taxonomy giả lập (id ổn định) — bộ vàng tham chiếu theo id này.
TOPICS = [
    SimpleNamespace(id=1, mach_noi_dung="Số tự nhiên", don_vi_kien_thuc="Số nguyên tố. Ước chung, bội chung"),
    SimpleNamespace(id=2, mach_noi_dung="Số nguyên", don_vi_kien_thuc="Số nguyên âm và tập hợp số nguyên"),
    SimpleNamespace(id=3, mach_noi_dung="Phân số", don_vi_kien_thuc="Phân số và các phép tính"),
    SimpleNamespace(id=4, mach_noi_dung="Hình học trực quan", don_vi_kien_thuc="Tam giác đều, hình vuông, lục giác đều"),
]


async def _main() -> None:
    cases = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    dung = 0
    try:
        for c in cases:
            got = await suggest_mapping(c["tag"], c["vi_du"], TOPICS)
            got_id = got[0] if got else None
            ok = got_id == c["topic_id_dung"]
            dung += ok
            print(f"[{'✓' if ok else '✗'}] {c['tag']!r}: dự đoán={got_id} / đúng={c['topic_id_dung']}")
    except LLMUnavailable as e:
        print(f"BỎ QUA eval: LLM không khả dụng (hết quota/khoá) — {str(e)[:80]}")
        return

    acc = dung / len(cases)
    print(f"\nĐộ chính xác ánh xạ: {dung}/{len(cases)} = {acc:.0%} (ngưỡng {NGUONG:.0%})")
    if acc < NGUONG:
        print("DƯỚI NGƯỠNG -> KHÔNG bật auto-map diện rộng, giữ người duyệt.")
    else:
        print("ĐẠT ngưỡng. Ánh xạ vẫn qua khâu duyệt theo thiết kế.")


if __name__ == "__main__":
    asyncio.run(_main())
