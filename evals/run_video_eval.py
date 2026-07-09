"""Eval chất lượng video (US-20) — QUALITY GATE trước khi phát hành.

Cổng CHẶN tất định (không xác suất): guard công thức phải phân loại đúng 100%
dataset vàng — kịch bản bám công thức thì ĐẠT, kịch bản bịa công thức thì BỊ
CHẶN. Sai công thức nguy hại hơn sai chữ (học sinh tin video), nên đây là gate
cứng.

Scenario 4: thiếu dataset -> BÁO RÕ là SKIPPED và trả mã lỗi (không coi là đạt),
CI không được phát hành khi eval bị bỏ qua.

    python -m evals.run_video_eval
"""

import json
import sys
from pathlib import Path

from app.video.guard import check_formulas
from app.video.script import Slide, Storyboard

DATASET = Path(__file__).resolve().parent / "video" / "dataset_video.jsonl"


def _load() -> list[dict]:
    if not DATASET.is_file():
        return []
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    rows = _load()
    if not rows:
        print("SKIPPED: thiếu dataset video -> KHÔNG coi là đạt, không phát hành.")
        return 2  # != 0: CI hiểu là chưa qua gate

    dung = 0
    for r in rows:
        sb = Storyboard(slides=[Slide(cong_thuc=r["script_formulas"], loi_thoai="x")])
        lech = check_formulas(sb, r["answer"])
        guard_ok = not lech
        khop = guard_ok == r["expect_ok"]
        dung += khop
        trang_thai = "OK" if khop else "SAI"
        print(f"[{trang_thai}] {r['concept']}: guard_ok={guard_ok}, expect={r['expect_ok']}")

    ty_le = dung / len(rows)
    NGUONG = 1.0  # gate công thức tất định: yêu cầu tuyệt đối
    print(f"\nĐộ chính xác guard công thức: {dung}/{len(rows)} = {ty_le:.0%} (ngưỡng {NGUONG:.0%})")
    if ty_le < NGUONG:
        print("KHÔNG ĐẠT gate video.")
        return 1
    print("ĐẠT gate video.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
