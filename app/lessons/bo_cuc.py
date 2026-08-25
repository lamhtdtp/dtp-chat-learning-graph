"""Bố cục 7 phần nội dung của một đơn vị kiến thức (REQ-demo-v2 §1).

Một chỗ duy nhất quyết định: phần nào hiện, thứ tự nào, và số thứ tự bao nhiêu.
Cả API học sinh, CMS và trợ lý đều gọi vào đây — tính lại ở mỗi nơi thì sớm muộn
số hiện cho học sinh lệch với số chuyên gia thấy khi soạn.
"""
import json

# Thứ tự CHUẨN (§1.1). `cot` = cột trong TopicContent, None = cột JSON riêng.
PHAN = (
    {"id": "khoi_dong", "ten": "Khởi động", "em": "🚀", "cot": "khoi_dong"},
    {"id": "hoat_dong", "ten": "Hoạt động", "em": "🧩", "cot": "hoat_dong"},
    {"id": "kien_thuc", "ten": "Kiến thức trọng tâm", "em": "💡", "cot": "khai_niem"},
    {"id": "minh_hoa", "ten": "Minh hoạ", "em": "🎬", "cot": None},
    {"id": "vi_du", "ten": "Ví dụ", "em": "✏️", "cot": None},
    {"id": "luyen_tap", "ten": "Luyện tập – Vận dụng", "em": "🎯", "cot": "luyen_tap"},
    {"id": "bai_tap", "ten": "Bài tập", "em": "📚", "cot": "bai_tap"},
)
IDS = tuple(p["id"] for p in PHAN)
_THEO_ID = {p["id"]: p for p in PHAN}


def doc(bo_cuc_json: str | None) -> list[dict]:
    """`bo_cuc_json` -> [{id, ten, em, cot, an}] theo thứ tự sẽ hiển thị.

    Chịu được dữ liệu rác: id lạ bị bỏ, phần thiếu được BỔ SUNG vào cuối theo thứ
    tự chuẩn. Nhờ vậy thêm phần mới vào PHAN sau này không cần migrate lại dữ liệu
    bố cục đã lưu — phần mới tự xuất hiện ở cuối thay vì biến mất.
    """
    try:
        raw = json.loads(bo_cuc_json or "[]")
    except json.JSONDecodeError:
        raw = []
    if not isinstance(raw, list):
        raw = []

    out, da_co = [], set()
    for x in raw:
        if not isinstance(x, dict):
            continue
        pid = x.get("id")
        if pid in _THEO_ID and pid not in da_co:
            da_co.add(pid)
            out.append({**_THEO_ID[pid], "an": bool(x.get("an"))})
    for p in PHAN:
        if p["id"] not in da_co:
            out.append({**p, "an": False})
    return out


def hien(bo_cuc_json: str | None) -> list[dict]:
    """Chỉ các phần HIỆN, kèm `so` = 1…n liền mạch.

    Phần ẩn không xuất hiện VÀ không chiếm số (§1.3): ẩn phần 2 thì phần 3 thành
    số 2, không để lỗ.
    """
    ds = [p for p in doc(bo_cuc_json) if not p["an"]]
    return [{**p, "so": i + 1} for i, p in enumerate(ds)]


def co_noi_dung(c, phan_id: str) -> bool:
    """Phần này có gì để hiển thị không?"""
    import json as _j

    if phan_id == "minh_hoa":
        cot = "minh_hoa_json"
    elif phan_id == "vi_du":
        cot = "vi_du_json"
    else:
        return bool(noi_dung(c, phan_id).strip())
    try:
        return bool(_j.loads(getattr(c, cot, None) or "[]"))
    except _j.JSONDecodeError:
        return False


def hien_thuc_te(c, bo_cuc_json: str | None) -> list[dict]:
    """Các phần THẬT SỰ hiện ra + số 1…n liền mạch.

    Khác `hien()`: bỏ luôn phần đang bật nhưng CHƯA CÓ NỘI DUNG. Nếu không, phần
    rỗng vẫn chiếm một số rồi client render null -> đề mục nhảy 1, 2, *4* (đã gặp
    thật khi bài chưa có minh hoạ). Đánh số phải trùng đúng cái học sinh nhìn thấy.
    """
    ds = [p for p in doc(bo_cuc_json) if not p["an"] and co_noi_dung(c, p["id"])]
    return [{**p, "so": i + 1} for i, p in enumerate(ds)]


def ghi(bo_cuc: list[dict]) -> str:
    """[{id, an}] -> JSON để lưu. Lược id lạ, khử trùng, giữ thứ tự client gửi."""
    out, da_co = [], set()
    for x in bo_cuc or []:
        pid = (x or {}).get("id")
        if pid in _THEO_ID and pid not in da_co:
            da_co.add(pid)
            out.append({"id": pid, "an": bool(x.get("an"))})
    return json.dumps(out, ensure_ascii=False)


def cot_cua(phan_id: str) -> str | None:
    """Tên cột lưu HTML của một phần. None = phần đó lưu ở cột JSON riêng
    (minh_hoa/vi_du) hoặc id không hợp lệ."""
    return _THEO_ID.get(phan_id, {}).get("cot")


def noi_dung(c, phan_id: str) -> str:
    """Nội dung HTML của một phần (rỗng nếu phần đó lưu ở cột JSON riêng)."""
    cot = _THEO_ID.get(phan_id, {}).get("cot")
    return (getattr(c, cot, "") or "") if cot else ""


def da_soan(c) -> int:
    """Số phần ĐÃ có nội dung, dùng cho "n/7 phần" ở CMS và % tiến độ mạch."""
    import json as _j

    n = sum(1 for p in PHAN if p["cot"] and (getattr(c, p["cot"], "") or "").strip())
    for cot in ("minh_hoa_json", "vi_du_json"):
        try:
            if _j.loads(getattr(c, cot, None) or "[]"):
                n += 1
        except _j.JSONDecodeError:
            pass
    return n
