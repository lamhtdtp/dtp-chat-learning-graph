"""Phần việc CMS cần cho màn “Nạp sách bằng AI” (REQ §2.4).

Tách khỏi `tasks.py` (vốn là orchestration cho CLI) vì việc ở đây khác hẳn: nhận
tệp người dùng kéo vào, SOÁT xem đủ trang chưa, đọc thử vài trang, rồi mới nạp.

Điểm dễ sai nhất của cả luồng là SỐ TRANG: pipeline lấy số trang từ tên tệp
(`_page_numbers` đọc `p.stem`), nên một quyển sách chụp bằng điện thoại với tên
`IMG_20250812_094512.jpg` sẽ vào kho với số trang vô nghĩa và mọi dẫn nguồn
“[tr.9]” trỏ sai bài. Vì vậy tệp không đoán được số trang KHÔNG được tự đặt số —
để riêng, chờ người soạn gán tay.
"""
import logging
import re
import shutil
from pathlib import Path

from app.ingestion.loaders.vision_page_loader import load_or_ocr_page
from app.ingestion.page_structure import detect_bai, detect_chuong
from app.ingestion.tasks import CACHE_ROOT, DATA_ROOT, _SUBJECT_FOLDER

log = logging.getLogger(__name__)

# Tệp chưa gán được số trang nằm tạm ở đây — CÙNG thư mục sách nhưng tên có tiền
# tố `_cho_`, để `*.png` của pipeline không quét phải (pipeline gọi int(p.stem)).
CHO_GAN = "_cho"
ANH_EXT = {".png", ".jpg", ".jpeg", ".webp"}
# Dưới mức này coi như trang gần trắng — thường là trang hình, bìa, hoặc ảnh mờ.
IT_CHU = 120

# Dấu hiệu OCR đã đọc được công thức. Với môn Toán đây là chỉ số đáng tin nhất
# của một lần đọc thử: `co_bai` thì hầu hết trang giữa bài đều False (chỉ trang
# MỞ ĐẦU bài mới có heading "Bài N"), nên dùng nó làm thước đo là báo động sai.
_DAU_TOAN = ("$", "\\frac", "\\dfrac", "\\sqrt", "\\times", "\\div", "\\cdot",
             "^{", "_{", "⋮", "≤", "≥", "≠", "×", "÷", "√")


def co_cong_thuc(md: str) -> bool:
    return any(d in md for d in _DAU_TOAN)


def thu_muc(mon: str, khoi: str, tap: int, tao: bool = False) -> Path:
    """Thư mục ảnh trang. Khác `tasks._book_dir`: luôn trả đường dẫn CÓ tập và
    tạo được thư mục — upload cần đích rõ ràng, không suy từ thư mục đã tồn tại."""
    d = DATA_ROOT / _SUBJECT_FOLDER.get(mon, mon) / khoi.removeprefix("lop_") / str(tap)
    if tao:
        d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(mon: str, tap: int) -> Path:
    return CACHE_ROOT / _SUBJECT_FOLDER.get(mon, mon) / f"tap{tap}"


def so_trang(ten: str) -> int | None:
    """Số trang suy từ tên tệp, hoặc None nếu không CHẮC.

    Chỉ nhận hai dạng: tên toàn số (`12.png`) hoặc có dãy ≥2 chữ số
    (`trang-045.png`). Cố ý khắt khe: `Scan (2).png` — tên Windows đặt cho bản
    sao — có số 2 trong đó, đoán bừa là ghi ĐÈ trang 2 thật của quyển sách.
    Thà để người soạn gán tay 3 tệp còn hơn mất một trang mà không ai biết.
    Ngưỡng trên 999 loại tên kiểu `IMG_20250812_094512`.
    """
    stem = Path(ten).stem.strip()
    if stem.isdigit():
        n = int(stem)
        return n if 1 <= n <= 999 else None
    so = [x for x in re.findall(r"\d+", stem) if len(x) >= 2]
    if not so:
        return None
    n = int(max(so, key=len))
    return n if 1 <= n <= 999 else None


def soat(mon: str, khoi: str, tap: int) -> dict:
    """Tình trạng thư mục sách: có trang nào, khuyết trang nào, tệp nào chờ gán.

    `thieu` chỉ tính TRONG khoảng trang đã có (min..max): sách chưa chụp hết thì
    không phải là thiếu, nhưng hổng ở giữa thì gần như chắc chắn bỏ sót.
    """
    d = thu_muc(mon, khoi, tap)
    co = sorted(int(p.stem) for p in d.glob("*.png") if p.stem.isdigit()) if d.is_dir() else []
    thieu = [n for n in range(co[0], co[-1] + 1) if n not in set(co)] if co else []

    cho = []
    kho = d / CHO_GAN
    if kho.is_dir():
        cho = sorted(
            ({"ten": p.name, "kb": round(p.stat().st_size / 1024)}
             for p in kho.iterdir() if p.suffix.lower() in ANH_EXT),
            key=lambda x: x["ten"])
    return {"mon": mon, "khoi": khoi, "tap": tap, "trang": co,
            "thieu": thieu, "cho_gan": cho,
            "da_ocr": sorted(int(p.stem) for p in cache_dir(mon, tap).glob("*.md")
                             if p.stem.isdigit()) if cache_dir(mon, tap).is_dir() else []}


def luu_tep(mon: str, khoi: str, tap: int, ten: str, data: bytes) -> dict:
    """Ghi một ảnh trang. Đoán được số trang thì lưu `<so>.png`, không thì để
    vào `_cho/` chờ gán tay — KHÔNG tự đặt số bừa."""
    d = thu_muc(mon, khoi, tap, tao=True)
    n = so_trang(ten)
    if n is None:
        kho = d / CHO_GAN
        kho.mkdir(parents=True, exist_ok=True)
        # Giữ nguyên tên gốc để người soạn nhận ra ảnh nào; đụng tên thì thêm hậu tố.
        dich = kho / Path(ten).name
        i = 1
        while dich.exists():
            dich = kho / f"{Path(ten).stem}_{i}{Path(ten).suffix}"
            i += 1
        dich.write_bytes(data)
        return {"ten": ten, "so": None, "cho_gan": dich.name}
    dich = d / f"{n}.png"
    ghi_de = dich.exists()          # nạp lại quyển cũ -> phải nói rõ, không im lặng
    dich.write_bytes(data)
    return {"ten": ten, "so": n, "cho_gan": None, "ghi_de": ghi_de}


def gan_so_trang(mon: str, khoi: str, tap: int, ten: str, so: int) -> int:
    """Gán số trang cho một tệp đang chờ: chuyển `_cho/<ten>` -> `<so>.png`."""
    d = thu_muc(mon, khoi, tap)
    nguon = d / CHO_GAN / Path(ten).name
    if not nguon.is_file():
        raise FileNotFoundError(f"Không còn tệp {ten} trong danh sách chờ gán")
    if not 1 <= so <= 999:
        raise ValueError("Số trang phải trong khoảng 1–999")
    shutil.move(str(nguon), str(d / f"{so}.png"))
    return so


def bo_tep_cho(mon: str, khoi: str, tap: int, ten: str) -> None:
    """Bỏ một tệp chờ gán (bìa, trang trắng, ảnh chụp lỗi)."""
    p = thu_muc(mon, khoi, tap) / CHO_GAN / Path(ten).name
    if p.is_file():
        p.unlink()


# Bỏ bao nhiêu phần đầu và cuối sách khi chọn trang đọc thử.
_BIA_LE = 0.12


def chon_trang_thu(trang: list[int], so_luong: int = 3) -> list[int]:
    """Trang để đọc thử: rải đều trong PHẦN RUỘT của sách.

    Cố ý bỏ ~12% đầu và cuối. Rải đều trên cả tập nghe hợp lý nhưng đo trên sách
    thật (Toán 6 tập 1, 151 trang) thì ra trang 1, 76, 151 — tức là BÌA SÁCH và
    BẢNG SỐ NGUYÊN TỐ ở phụ lục. Hai trang đó OCR đúng hay sai đều không nói được
    gì về việc đọc nổi công thức trong bài học, mà đó mới là chỗ hay vỡ.
    """
    if not trang:
        return []
    n = min(so_luong, len(trang))
    bo = int(len(trang) * _BIA_LE)
    ruot = trang[bo:len(trang) - bo] or trang        # sách quá mỏng thì lấy hết
    if n == 1:
        return [ruot[len(ruot) // 2]]
    if n >= len(ruot):
        return list(ruot)
    buoc = (len(ruot) - 1) / (n - 1)
    return sorted({ruot[round(i * buoc)] for i in range(n)})


async def doc_thu(mon: str, khoi: str, tap: int, trang: list[int],
                  lam_lai: bool = False) -> list[dict]:
    """OCR vài trang và trả kèm dấu hiệu chất lượng. KHÔNG ghi Qdrant.

    Chỉ số chính là `co_cong_thuc` — với sách Toán, OCR vỡ ở công thức chứ không
    vỡ ở chữ. `co_bai`/`co_chuong` trả kèm nhưng CHỈ để tham khảo: hầu hết trang
    giữa bài không có heading "Bài N" nên chúng False là bình thường.
    """
    d, c = thu_muc(mon, khoi, tap), cache_dir(mon, tap)
    ra = []
    for n in trang:
        anh = d / f"{n}.png"
        if not anh.is_file():
            ra.append({"so": n, "loi": "không có ảnh trang này"})
            continue
        try:
            md = await load_or_ocr_page(anh, c / f"{n}.md", force=lam_lai, mon=mon)
        except Exception as e:                    # noqa: BLE001 - báo lỗi từng trang
            log.warning("Đọc thử trang %s lỗi: %s", n, e)
            ra.append({"so": n, "loi": str(e)[:200]})
            continue
        ra.append({
            "so": n, "md": md, "chu": len(md.strip()),
            "co_cong_thuc": co_cong_thuc(md),
            "co_chuong": detect_chuong(md) is not None,
            "co_bai": detect_bai(md) is not None,
            "it_chu": len(md.strip()) < IT_CHU,
        })
    return ra
