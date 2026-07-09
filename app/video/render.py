"""Dựng slide cho video (US-18).

Nguyên tắc: MODEL KHÔNG tự vẽ công thức. Công thức được KaTeX kiểm tra cú pháp
(deterministic) — cú pháp sai thì "vỡ công thức" bị bắt ngay, không lọt vào
video. Ảnh slide vẽ bằng Pillow (tất định: cùng input -> cùng bytes).

Ghi chú triển khai: raster hoá KaTeX-HTML thành ảnh cần headless browser (prod
dùng chrome/puppeteer). Ở đây chưa có browser nên slide hiển thị công thức dạng
Unicode dễ đọc; KaTeX vẫn được dùng để VALIDATE cú pháp (không vẽ ẩu công thức
sai). Đổi sang raster KaTeX thật = thay mỗi hàm render_slide, không đụng pipeline.
"""

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.video.script import Slide

_KATEX_MAIN = Path(__file__).resolve().parents[2] / "web" / "node_modules" / "katex"
_FONT = "/Library/Fonts/Arial Unicode.ttf"  # hỗ trợ tiếng Việt + ký hiệu toán

_W, _H = 1280, 720
_BG = (247, 250, 255)
_BLUE = (27, 79, 191)
_INK = (31, 42, 68)


class KaTeXError(Exception):
    """Công thức LaTeX sai cú pháp -> 'vỡ công thức', chặn không cho vào video."""


def katex_validate(latex: str) -> str:
    """Render LaTeX qua KaTeX (throwOnError). Trả HTML nếu hợp lệ; raise KaTeXError
    nếu cú pháp sai. Deterministic — cùng input, cùng output."""
    script = (
        f"const katex=require({json.dumps(str(_KATEX_MAIN))});"
        "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
        "try{process.stdout.write(katex.renderToString(s,{throwOnError:true}));}"
        "catch(e){process.stderr.write(String(e));process.exit(3);}});"
    )
    proc = subprocess.run(
        ["node", "-e", script], input=latex, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise KaTeXError(f"LaTeX không hợp lệ: {latex!r} — {proc.stderr[:200]}")
    return proc.stdout


# Bản đồ ký hiệu LaTeX -> Unicode để hiển thị slide dễ đọc (best-effort, tất định).
_SUB = {
    r"\cdot": "·", r"\times": "×", r"\div": "÷", r"\le": "≤", r"\ge": "≥",
    r"\ne": "≠", r"\pm": "±", r"\sqrt": "√", r"\pi": "π", r"\Rightarrow": "⇒",
    "*": "×", "\\,": " ", "\\!": "", "{": "", "}": "",
}


def latex_to_unicode(latex: str) -> str:
    out = latex
    for k, v in _SUB.items():
        out = out.replace(k, v)
    # mũ đơn giản a^2 -> a² (chỉ 1 ký tự) cho dễ đọc trên slide
    supers = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
              "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "n": "ⁿ"}
    import re
    out = re.sub(r"\^(\w)", lambda m: supers.get(m.group(1), "^" + m.group(1)), out)
    return out.strip()


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT, size)
    except OSError:
        return ImageFont.load_default()


def render_slide(slide: Slide, out_path: str | Path, *, index: int = 0, total: int = 1) -> Path:
    """Vẽ 1 slide PNG 1280x720. Validate mọi công thức qua KaTeX trước (sai cú
    pháp -> KaTeXError, không tạo slide hỏng)."""
    for ct in slide.cong_thuc:
        katex_validate(ct)

    img = Image.new("RGB", (_W, _H), _BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, _W, 88], fill=_BLUE)
    d.text((56, 26), slide.tieu_de or "Ôn tập", font=_font(40), fill=(255, 255, 255))
    d.text((_W - 150, 34), f"{index + 1}/{total}", font=_font(26), fill=(210, 224, 255))

    y = 150
    for bullet in slide.y_chinh:
        d.ellipse([60, y + 12, 74, y + 26], fill=_BLUE)
        d.text((92, y), bullet, font=_font(32), fill=_INK)
        y += 62

    for ct in slide.cong_thuc:
        d.text((92, y + 10), latex_to_unicode(ct), font=_font(46), fill=_BLUE)
        y += 78

    out = Path(out_path)
    img.save(out, "PNG")
    return out
