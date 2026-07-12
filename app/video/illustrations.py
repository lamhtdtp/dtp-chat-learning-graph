"""Minh hoạ toán vẽ động theo TỪNG khái niệm (Pillow), dùng trong animate.py.

Mỗi drawer vẽ trong vùng ~ 360x360 quanh tâm (cx, cy): `t` là tiến độ hiện
(0..1 trong slide, để reveal), `frame` là số frame tuyệt đối (để chuyển động
liên tục). Không random -> tất định. Khái niệm chưa có hình riêng -> fallback.
"""

import math

from PIL import ImageDraw, ImageFont

from app.video.fonts import FONT_PATH as _FONT
_BLUE = (43, 111, 246)
_INK = (28, 39, 66)
_GREEN = (76, 168, 115)
_ORANGE = (233, 160, 54)
_RED = (216, 84, 84)
_LINE = (150, 168, 200)


def _f(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT, size)
    except OSError:
        return ImageFont.load_default()


def _ctext(d, x, y, s, font, fill):
    w = d.textlength(s, font=font)
    d.text((x - w / 2, y), s, font=font, fill=fill)


def _pulse(frame: int, amp: float = 1.0) -> float:
    return amp * math.sin(frame / 25 * 2)


# ---- trục số: số nguyên âm/dương ----
def _number_line(d, cx, cy, t, frame):
    x0, x1 = cx - 170, cx + 170
    d.line([x0, cy, x1, cy], fill=_LINE, width=4)
    d.polygon([(x1, cy), (x1 - 14, cy - 8), (x1 - 14, cy + 8)], fill=_LINE)
    d.polygon([(x0, cy), (x0 + 14, cy - 8), (x0 + 14, cy + 8)], fill=_LINE)
    for i in range(-3, 4):
        x = cx + i * 48
        d.line([x, cy - 8, x, cy + 8], fill=_LINE, width=3)
        col = _RED if i < 0 else (_INK if i > 0 else _BLUE)
        _ctext(d, x, cy + 16, str(i), _f(22), col)
    # điểm chạy dọc trục theo thời gian
    pos = int((-3 + 6 * t))
    mx = cx + pos * 48
    r = 12 + _pulse(frame, 2)
    d.ellipse([mx - r, cy - r, mx + r, cy + r], fill=_BLUE)


# ---- tập hợp: vòng + phần tử, 1 phần tử ngoài ----
def _set_circle(d, cx, cy, t, frame):
    R = 95
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=_BLUE, width=5)
    _ctext(d, cx, cy - R - 34, "A", _f(30), _BLUE)
    pts = [(-40, -20), (30, -30), (0, 25), (45, 20)]
    n = max(1, int(len(pts) * min(1.0, t / 0.7)))
    for i, (dx, dy) in enumerate(pts[:n]):
        d.ellipse([cx + dx - 12, cy + dy - 12, cx + dx + 12, cy + dy + 12], fill=_GREEN)
    # phần tử NGOÀI tập hợp
    ox, oy = cx + R + 55, cy
    d.ellipse([ox - 12, oy - 12, ox + 12, oy + 12], fill=_RED)
    _ctext(d, ox, oy + 18, "∉ A", _f(22), _RED)


# ---- số nguyên tố: số và đúng hai ước 1 và chính nó ----
def _prime(d, cx, cy, t, frame):
    _ctext(d, cx, cy - 70, "7", _f(96), _BLUE)
    if t > 0.3:
        _ctext(d, cx - 90, cy + 60, "1", _f(40), _GREEN)
        _ctext(d, cx + 90, cy + 60, "7", _f(40), _GREEN)
        d.line([cx - 20, cy + 30, cx - 80, cy + 60], fill=_LINE, width=3)
        d.line([cx + 20, cy + 30, cx + 80, cy + 60], fill=_LINE, width=3)
        _ctext(d, cx, cy + 120, "chỉ 2 ước", _f(24), _INK)


# ---- lũy thừa: a·a·a = a³ ----
def _power(d, cx, cy, t, frame):
    n = 3
    show = max(1, int(n * min(1.0, t / 0.6)))
    parts = " · ".join(["2"] * show)
    _ctext(d, cx, cy - 20, parts, _f(48), _INK)
    if t > 0.7:
        _ctext(d, cx, cy + 50, "= 2³", _f(54), _BLUE)


# ---- ước chung / bội chung: 2 vòng giao nhau (Venn) ----
def _venn(d, cx, cy, t, frame):
    R = 78
    d.ellipse([cx - R - 45, cy - R, cx - 45 + R, cy + R], outline=_BLUE, width=5)
    d.ellipse([cx + 45 - R, cy - R, cx + 45 + R, cy + R], outline=_GREEN, width=5)
    if t > 0.4:  # phần giao tô nổi
        d.ellipse([cx - 40, cy - 38, cx + 40, cy + 38], fill=_ORANGE)
        _ctext(d, cx, cy - 12, "chung", _f(24), (255, 255, 255))


# ---- chu vi & diện tích: hình chữ nhật, tô diện tích ----
def _rectangle(d, cx, cy, t, frame):
    w, h = 210, 130
    x0, y0 = cx - w // 2, cy - h // 2
    if t > 0.3:
        d.rectangle([x0, y0, x0 + w, y0 + h], fill=(220, 234, 255))
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=_BLUE, width=5)
    _ctext(d, cx, y0 - 34, "chiều dài", _f(22), _INK)
    d.text((x0 + w + 12, cy - 12), "rộng", font=_f(22), fill=_INK)


# ---- tam giác đều ----
def _triangle(d, cx, cy, t, frame):
    s = 150
    p1 = (cx, cy - s * 0.6)
    p2 = (cx - s * 0.55, cy + s * 0.45)
    p3 = (cx + s * 0.55, cy + s * 0.45)
    d.polygon([p1, p2, p3], outline=_BLUE, width=5)
    for a, b in [(p1, p2), (p2, p3), (p3, p1)]:  # dấu bằng nhau
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        d.line([mx - 6, my - 6, mx + 6, my + 6], fill=_GREEN, width=4)


# ---- góc: hai tia + cung ----
def _angle(d, cx, cy, t, frame):
    vx, vy = cx - 60, cy + 60
    d.line([vx, vy, vx + 220, vy], fill=_INK, width=5)
    ang = math.radians(50)
    d.line([vx, vy, vx + 210 * math.cos(-ang), vy + 210 * math.sin(-ang)], fill=_INK, width=5)
    d.arc([vx - 45, vy - 45, vx + 45, vy + 45], -50, 0, fill=_BLUE, width=5)
    _ctext(d, vx + 70, vy - 55, "góc", _f(24), _BLUE)


# ---- đoạn thẳng & trung điểm ----
def _segment(d, cx, cy, t, frame):
    x0, x1 = cx - 160, cx + 160
    d.line([x0, cy, x1, cy], fill=_INK, width=5)
    for x, lb, col in [(x0, "A", _INK), (cx, "M", _RED), (x1, "B", _INK)]:
        d.ellipse([x - 9, cy - 9, x + 9, cy + 9], fill=col)
        _ctext(d, x, cy - 40, lb, _f(28), col)
    if t > 0.5:
        _ctext(d, (x0 + cx) // 2, cy + 20, "=", _f(30), _GREEN)
        _ctext(d, (cx + x1) // 2, cy + 20, "=", _f(30), _GREEN)


# ---- tỉ số phần trăm: hình tròn khuyết ----
def _percent(d, cx, cy, t, frame):
    R = 95
    deg = int(360 * 0.35 * min(1.0, t / 0.8))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(226, 236, 255))
    d.pieslice([cx - R, cy - R, cx + R, cy + R], -90, -90 + deg, fill=_BLUE)
    _ctext(d, cx, cy - 16, "35%", _f(34), _INK)


# ---- phân số: thanh chia phần, tô phần tử số ----
def _fraction(d, cx, cy, t, frame):
    w, h, parts, shaded = 260, 70, 4, 3
    x0, y0 = cx - w // 2, cy - h // 2
    pw = w / parts
    for i in range(parts):
        x = x0 + i * pw
        if i < shaded and t > 0.2 + i * 0.15:
            d.rectangle([x, y0, x + pw, y0 + h], fill=_BLUE)
        d.rectangle([x, y0, x + pw, y0 + h], outline=_INK, width=3)
    _ctext(d, cx, y0 + h + 16, "3/4", _f(30), _BLUE)


# ---- dấu hiệu chia hết: số, chữ số cuối nổi bật ----
def _divisible(d, cx, cy, t, frame):
    _ctext(d, cx - 30, cy - 30, "12", _f(72), _INK)
    if t > 0.3:
        d.rounded_rectangle([cx + 20, cy - 34, cx + 78, cy + 40], radius=8, outline=_RED, width=5)
        _ctext(d, cx + 49, cy - 30, "2", _f(72), _RED)
        _ctext(d, cx, cy + 70, "chữ số tận cùng", _f(22), _INK)


# ---- số thập phân: dấu phẩy nổi bật ----
def _decimal(d, cx, cy, t, frame):
    _ctext(d, cx, cy - 30, "3,14", _f(72), _INK)
    if t > 0.4:
        d.ellipse([cx - 10, cy + 34, cx + 6, cy + 50], fill=_RED)
        _ctext(d, cx, cy + 60, "phần thập phân", _f(22), _INK)


# ---- ước & bội: a chia hết b ----
def _uocboi(d, cx, cy, t, frame):
    _ctext(d, cx - 90, cy, "12", _f(56), _BLUE)
    _ctext(d, cx + 90, cy, "3", _f(56), _GREEN)
    d.line([cx - 40, cy + 20, cx + 50, cy + 20], fill=_LINE, width=4)
    d.polygon([(cx + 50, cy + 20), (cx + 38, cy + 12), (cx + 38, cy + 28)], fill=_LINE)
    _ctext(d, cx, cy + 40, "chia hết", _f(22), _INK)


# ---- fallback: các chấm màu xoay quanh tâm ----
def _fallback(d, cx, cy, t, frame):
    base = frame / 25
    palette = [_BLUE, _GREEN, _ORANGE, _RED]
    for i in range(4):
        ang = base * 0.9 + i * (math.pi / 2)
        r = 72 + 12 * math.sin(base * 1.6 + i)
        x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
        rad = 15 + 5 * math.sin(base * 2 + i)
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=palette[i])
    d.ellipse([cx - 32, cy - 32, cx + 32, cy + 32], outline=_BLUE, width=4)


_REGISTRY = {
    "so_nguyen_am": _number_line,
    "tap_hop": _set_circle,
    "so_nguyen_to": _prime,
    "luy_thua": _power,
    "uoc_chung_lon_nhat": _venn,
    "boi_chung_nho_nhat": _venn,
    "chu_vi_dien_tich": _rectangle,
    "tam_giac_deu": _triangle,
    "goc": _angle,
    "doan_thang_trung_diem": _segment,
    "ti_so_phan_tram": _percent,
    "phan_so": _fraction,
    "dau_hieu_chia_het": _divisible,
    "so_thap_phan": _decimal,
    "uoc_va_boi": _uocboi,
}


def draw(slug: str | None, d: ImageDraw.ImageDraw, cx: int, cy: int, t: float, frame: int) -> None:
    _REGISTRY.get(slug or "", _fallback)(d, cx, cy, t, frame)
