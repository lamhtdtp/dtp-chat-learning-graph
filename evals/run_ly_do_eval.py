"""Eval chất lượng LÝ DO TỪNG PHƯƠNG ÁN theo nội dung câu trên tờ đề (US-30 Kịch bản 17, ngưỡng của
US-26 Kịch bản 23). Cổng xác suất: chạy thật qua `app.llm.gateway` (tầng rẻ sinh lý do, tầng mạnh làm
giám khảo), KHÔNG chạy trong bộ test thường vì tốn quota.

    python -m evals.run_ly_do_eval [--gioi-han N] [--ghi ket_qua.json]

Dataset `evals/dataset_ly_do.jsonl` (mỗi dòng một câu không hình):
  * `nhom="kho"`   — 36 câu Toán 6 cuối kỳ 1 và 2, đủ ba dạng (12 một đáp án, 12 nhiều đáp án, 12 đúng-sai).
  * `nhom="da_sua"`— 12 câu "đã sửa so với kho": nội dung tờ đề (các trường gốc của dòng) khác bản kho
    (`kho`) ở đáp án, một phương án hoặc số liệu; `kho_dau_hieu` là các chuỗi CHỈ có ở bản kho.
  LƯU Ý: đây là câu TỰ SOẠN theo dạng đề cuối kỳ Toán 6, chưa phải câu rút từ kho DTP Testbank thật
  (repo mã không có kho). Khi có kho, thay / bổ sung dòng cùng định dạng.

Tiêu chí (cùng ngưỡng US-26 KB 23, thêm tập câu đã sửa):
  1. Không lý do nào mâu thuẫn đáp án của tờ đề: 100%. Kiểm TỰ ĐỘNG theo nhãn đúng / sai (từ khoá phủ định
     / khẳng định trái nhãn) và thêm cờ của giám khảo.
  2. Đúng toán học và bám lời giải của tờ đề: >= 90% số lý do (giám khảo LLM).
  3. Đưa kiến thức ngoài chương trình / ngoài lời giải: <= 2% (giám khảo LLM).
  4. Tập câu đã sửa: 0 lý do nói theo đáp án / số liệu của kho (chuỗi `kho_dau_hieu` hoặc cờ giám khảo).

Giám khảo LLM CHƯA được hiệu chuẩn với người chấm (cần >= 20 mẫu người chấm theo US-30) — con số 2 và 3 là
số của giám khảo, chưa phải số của người. Báo cáo in rõ điều này.

Mã thoát: 0 đạt cả bốn · 1 không đạt · 2 không chạy được (thiếu dataset / model không trả lời).
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from app.exam import ly_do as ly_do_svc
from app.exam import ly_do_to_de
from app.llm import gateway, jsonfix
from app.llm.gateway import LLMUnavailable

DATASET = Path(__file__).resolve().parent / "dataset_ly_do.jsonl"
NGUONG_DUNG_TOAN = 0.90
NGUONG_NGOAI_CT = 0.02
_SONG_SONG = 4

# Từ khoá phủ định đặt vào lý do của phương án ĐÚNG, và khẳng định đặt vào lý do của phương án SAI.
_PHU_DINH_O_PA_DUNG = ("không đúng", "chưa đúng", "không chính xác", "là sai", "sai vì", "em chọn sai",
                       "không phải đáp án", "không phải là đáp án", "chưa chính xác")
_KHANG_DINH_O_PA_SAI = ("là đáp án đúng", "đáp án đúng là", "đúng vì", "vì sao đúng", "khẳng định này đúng",
                        "ý này đúng", "phương án này đúng", "đây là đáp án")
_PHU_DINH_TRUOC = ("không", "chưa", "chẳng", "đâu phải", "không phải")


def _co_khang_dinh(ly_do: str, cum: tuple[str, ...]) -> bool:
    """Có một cụm trong `cum` xuất hiện mà KHÔNG đứng ngay sau từ phủ định ("không phải là đáp án đúng")."""
    t = " ".join(ly_do.lower().split())
    for c in cum:
        for m in re.finditer(re.escape(c), t):
            truoc = t[max(0, m.start() - 12):m.start()].strip()
            if not truoc.endswith(_PHU_DINH_TRUOC):
                return True
    return False


def mau_thuan_nhan(cau: dict, ly_do: dict[str, str]) -> list[str]:
    """Các phương án có lý do MÂU THUẪN nhãn đúng / sai của tờ đề (kiểm tự động theo từ khoá). `cau` là
    câu dạng kho (`ly_do_to_de.cau_kieu_kho`). Không bắt được mọi ca (đó là việc của giám khảo) nhưng
    không bao giờ báo oan một lý do nói đúng nhãn."""
    dung = ly_do_svc.dung_sai(cau)
    sai = []
    for k, t in ly_do.items():
        if dung.get(k) and _co_khang_dinh(t, _PHU_DINH_O_PA_DUNG):
            sai.append(k)
        elif dung.get(k) is False and _co_khang_dinh(t, _KHANG_DINH_O_PA_SAI):
            sai.append(k)
    return sorted(sai)


def theo_kho(ly_do: dict[str, str], dau_hieu: list[str]) -> list[str]:
    """Các phương án có lý do chứa chuỗi chỉ có ở bản kho."""
    return sorted(k for k, t in ly_do.items() if any(d and d in t for d in dau_hieu))


def tao_prompt_giam_khao(r: dict, ly_do: dict[str, str]) -> str:
    cau = ly_do_to_de.cau_kieu_kho({**r, "phuong_an": r["phuong_an"], "khoi_du_kien": "", "qid": r["id"],
                                    "phien_ban": "V01", "de_bai": r["de_bai"]})
    dung = ly_do_svc.dung_sai(cau)
    pa = "\n".join(f"{p['khoa']}. {p['noi_dung']} — {'ĐÚNG' if dung[p['khoa']] else 'SAI'}" for p in r["phuong_an"])
    ld = "\n".join(f"{k}: {v}" for k, v in sorted(ly_do.items()))
    kho = ""
    if r.get("kho"):
        k = r["kho"]
        kho = ("\nBẢN KHO GỐC (KHÔNG phải tờ đề — lý do không được nói theo bản này):\n"
               f"Đề: {k['de_bai']}\nPhương án: " + "; ".join(f"{p['khoa']}. {p['noi_dung']}" for p in k["phuong_an"])
               + f"\nĐáp án kho: {k['dap_an']}\n")
    return f"""Em là giám khảo chấm lý do giải thích từng phương án của một câu Toán lớp 6. Lý do do AI viết.
TỜ ĐỀ (nguồn đúng duy nhất):
Đề: {r['de_bai']}
Phương án (đã ghi đúng / sai theo tờ đề):
{pa}
Đáp án tờ đề: {r['dap_an']}
Lời giải tờ đề: {r['bai_giai']}
{kho}
LÝ DO CẦN CHẤM:
{ld}

Với MỖI phương án, trả về các cờ true/false:
- "dung_toan": lý do đúng về toán học VÀ phù hợp lời giải / nhãn đúng-sai của tờ đề.
- "mau_thuan": lý do khẳng định ngược nhãn đúng / sai của tờ đề.
- "ngoai_chuong_trinh": lý do đưa kiến thức ngoài chương trình Toán 6 hoặc ngoài lời giải của tờ đề.
- "theo_kho": lý do nói theo đáp án / số liệu của BẢN KHO GỐC thay vì của tờ đề (chỉ có nghĩa khi có bản kho).
Chỉ trả về JSON, khoá là chữ cái phương án, ví dụ: {{"A": {{"dung_toan": true, "mau_thuan": false, "ngoai_chuong_trinh": false, "theo_kho": false}}}}"""


async def _sinh_va_cham(r: dict, khoa: asyncio.Semaphore) -> dict:
    cau = ly_do_to_de.cau_kieu_kho({**r, "qid": r["id"], "phien_ban": "V01", "khoi_du_kien": ""})
    async with khoa:
        ly = await ly_do_svc.sinh_ly_do(cau)
        if ly is None:
            return {"id": r["id"], "loi": "model không trả lời"}
        if not ly:
            return {"id": r["id"], "ly_do": {}, "thieu": [o["key"] for o in cau["options"]], "giam_khao": {}}
        try:
            raw = await gateway.complete("eval_judge", [{"role": "user", "content": tao_prompt_giam_khao(r, ly)}],
                                         max_tokens=3000)
        except LLMUnavailable as e:
            return {"id": r["id"], "loi": f"giám khảo không trả lời ({e})"}
    gk = jsonfix.boc_json(raw)
    gk = gk if isinstance(gk, dict) else {}
    return {"id": r["id"], "ly_do": ly, "thieu": [o["key"] for o in cau["options"] if o["key"] not in ly],
            "giam_khao": {k: v for k, v in gk.items() if isinstance(v, dict)}}


def tong_hop(rows: list[dict], ket: list[dict]) -> dict:
    """Số đo + đạt / không từng tiêu chí. Hàm thuần (test được): `rows` dataset, `ket` kết quả từng câu."""
    theo_id = {r["id"]: r for r in rows}
    tong = dung_toan = ngoai = mau_thuan = mt_gk = theo_kho_n = da_sua_ly_do = 0
    chi_tiet = []
    for k in ket:
        if "loi" in k:
            continue
        r = theo_id[k["id"]]
        cau = ly_do_to_de.cau_kieu_kho({**r, "qid": r["id"], "phien_ban": "V01", "khoi_du_kien": ""})
        mt = mau_thuan_nhan(cau, k["ly_do"])
        kho = theo_kho(k["ly_do"], r.get("kho_dau_hieu") or []) if r["nhom"] == "da_sua" else []
        for key in k["ly_do"]:
            g = k["giam_khao"].get(key, {})
            tong += 1
            dung_toan += bool(g.get("dung_toan")) and not g.get("mau_thuan")
            ngoai += bool(g.get("ngoai_chuong_trinh"))
            mt_gk += bool(g.get("mau_thuan"))
            if r["nhom"] == "da_sua":
                da_sua_ly_do += 1
                theo_kho_n += (key in kho) or bool(g.get("theo_kho"))
        mau_thuan += len(mt)
        if mt or kho:
            chi_tiet.append({"id": r["id"], "mau_thuan_nhan": mt, "theo_kho": kho})
    bi_loi = [k for k in ket if "loi" in k]
    return {
        "so_cau": len(ket) - len(bi_loi), "so_ly_do": tong, "cau_loi": [(k["id"], k["loi"]) for k in bi_loi],
        "mau_thuan_tu_dong": mau_thuan, "mau_thuan_giam_khao": mt_gk,
        "ti_le_dung_toan_bam_loi_giai": dung_toan / tong if tong else 0.0,
        "ti_le_ngoai_chuong_trinh": ngoai / tong if tong else 1.0,
        "da_sua_so_ly_do": da_sua_ly_do, "da_sua_theo_kho": theo_kho_n,
        "chi_tiet": chi_tiet,
        "dat": {
            "mau_thuan": bool(tong) and mau_thuan == 0 and mt_gk == 0,
            "dung_toan": bool(tong) and dung_toan / tong >= NGUONG_DUNG_TOAN,
            "ngoai_chuong_trinh": bool(tong) and ngoai / tong <= NGUONG_NGOAI_CT,
            "da_sua_khong_theo_kho": theo_kho_n == 0 and da_sua_ly_do > 0,
        },
    }


def _doc() -> list[dict]:
    if not DATASET.is_file():
        return []
    return [json.loads(d) for d in DATASET.read_text(encoding="utf-8").splitlines() if d.strip()]


async def chay(gioi_han: int | None = None) -> tuple[list[dict], list[dict]]:
    rows = _doc()
    if gioi_han:
        # Lấy đều ba dạng + nhóm đã sửa, không cắt đầu file (sẽ chỉ còn một dạng).
        rows = rows[::max(1, len(rows) // gioi_han)][:gioi_han]
    khoa = asyncio.Semaphore(_SONG_SONG)
    return rows, list(await asyncio.gather(*(_sinh_va_cham(r, khoa) for r in rows)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gioi-han", type=int, default=None, help="chỉ chạy N câu (lấy đều) để thử nhanh")
    ap.add_argument("--ghi", type=Path, default=None, help="ghi kết quả chi tiết ra file JSON")
    a = ap.parse_args()
    rows, ket = asyncio.run(chay(a.gioi_han))
    if not rows:
        print("SKIPPED: thiếu dataset lý do từng phương án -> KHÔNG coi là đạt.")
        return 2
    kq = tong_hop(rows, ket)
    if a.ghi:
        a.ghi.write_text(json.dumps({"tong_hop": kq, "ket": ket}, ensure_ascii=False, indent=1), encoding="utf-8")
    nhom = {n: sum(1 for r in rows if r["nhom"] == n) for n in ("kho", "da_sua")}
    print(f"Câu chạy: {len(rows)} (kho {nhom['kho']}, đã sửa {nhom['da_sua']}) — câu có kết quả: {kq['so_cau']}, "
          f"lý do chấm: {kq['so_ly_do']}")
    for i, l in kq["cau_loi"]:
        print(f"  KHÔNG CHẠY ĐƯỢC {i}: {l}")
    if not kq["so_ly_do"]:
        print("KHÔNG ĐO ĐƯỢC: model không trả lý do nào (hết quota / lỗi) -> không coi là đạt.")
        return 2
    d = kq["dat"]
    print(f"1. Mâu thuẫn đáp án tờ đề: tự động {kq['mau_thuan_tu_dong']}, giám khảo {kq['mau_thuan_giam_khao']} "
          f"(ngưỡng 0) -> {'ĐẠT' if d['mau_thuan'] else 'KHÔNG ĐẠT'}")
    print(f"2. Đúng toán + bám lời giải tờ đề: {kq['ti_le_dung_toan_bam_loi_giai']:.1%} "
          f"(ngưỡng >= {NGUONG_DUNG_TOAN:.0%}) -> {'ĐẠT' if d['dung_toan'] else 'KHÔNG ĐẠT'}")
    print(f"3. Kiến thức ngoài chương trình / lời giải: {kq['ti_le_ngoai_chuong_trinh']:.1%} "
          f"(ngưỡng <= {NGUONG_NGOAI_CT:.0%}) -> {'ĐẠT' if d['ngoai_chuong_trinh'] else 'KHÔNG ĐẠT'}")
    print(f"4. Câu đã sửa — lý do theo kho: {kq['da_sua_theo_kho']}/{kq['da_sua_so_ly_do']} (ngưỡng 0) -> "
          f"{'ĐẠT' if d['da_sua_khong_theo_kho'] else 'KHÔNG ĐẠT'}")
    for c in kq["chi_tiet"]:
        print(f"   - {c['id']}: mâu thuẫn nhãn {c['mau_thuan_nhan']}, theo kho {c['theo_kho']}")
    print("Lưu ý: giám khảo LLM chưa hiệu chuẩn với người chấm; dataset là câu tự soạn, chưa phải câu kho thật.")
    return 0 if all(d.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
