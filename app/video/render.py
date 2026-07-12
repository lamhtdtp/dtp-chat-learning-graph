"""Tiện ích cho video (US-18): validate công thức bằng KaTeX + đổi LaTeX sang
Unicode để hiển thị trên slide. Dựng frame hoạt hình ở app/video/animate.py.

Nguyên tắc: MODEL KHÔNG tự vẽ công thức. Công thức được KaTeX kiểm tra cú pháp
(deterministic) — sai cú pháp thì "vỡ công thức" bị bắt ngay, không lọt vào
video. Raster KaTeX thật (đẹp hơn) cần headless browser ở prod; ở đây hiển thị
công thức dạng Unicode dễ đọc, KaTeX vẫn dùng để VALIDATE.
"""

import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.video.fonts import FONT_PATH as _FONT  # macOS/Linux tự chọn font (tiếng Việt + ký hiệu)
from app.video.script import Slide

_KATEX_MAIN = Path(__file__).resolve().parents[2] / "web" / "node_modules" / "katex"

_W, _H = 1280, 720
_BG = (247, 250, 255)
_BLUE = (27, 79, 191)
_INK = (31, 42, 68)

# Placeholder giữ ngoặc tập hợp \{ \} khỏi bị xoá cùng ngoặc gom nhóm {}.
_LBRACE, _RBRACE = "", ""


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


# LaTeX -> Unicode để hiển thị công thức dễ đọc. Thứ tự QUAN TRỌNG: lệnh dài
# thay trước lệnh ngắn (\notin trước \in, \leq trước \le) để không thay nhầm.
_SUB = [
    (r"\mathbb{N}", "ℕ"), (r"\mathbb{Z}", "ℤ"), (r"\mathbb{Q}", "ℚ"), (r"\mathbb{R}", "ℝ"),
    (r"\notin", "∉"), (r"\in", "∈"), (r"\leq", "≤"), (r"\le", "≤"),
    (r"\geq", "≥"), (r"\ge", "≥"), (r"\neq", "≠"), (r"\ne", "≠"),
    (r"\subseteq", "⊆"), (r"\subset", "⊂"), (r"\cup", "∪"), (r"\cap", "∩"),
    (r"\varnothing", "∅"), (r"\emptyset", "∅"), (r"\cdot", "·"), (r"\times", "×"),
    (r"\div", "÷"), (r"\pm", "±"), (r"\sqrt", "√"), (r"\pi", "π"),
    (r"\Rightarrow", "⇒"), (r"\rightarrow", "→"), (r"\to", "→"),
    (r"\ldots", "…"), (r"\dots", "…"), (r"\mid", "∣"), (r"\vert", "|"),
    (r"\left", ""), (r"\right", ""), (r"\,", " "), (r"\!", ""), (r"\;", " "),
]
_SUPERS = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
           "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "n": "ⁿ", "m": "ᵐ"}


def latex_to_unicode(latex: str) -> str:
    out = latex.replace(r"\{", _LBRACE).replace(r"\}", _RBRACE)
    for k, v in _SUB:
        out = out.replace(k, v)
    out = out.replace("*", "×")
    # mũ: ^{...} và ^x -> chữ số trên nếu được, ngược lại ^(...)
    out = re.sub(
        r"\^\{([^}]*)\}",
        lambda m: "".join(_SUPERS[c] for c in m.group(1))
        if all(c in _SUPERS for c in m.group(1)) else f"^({m.group(1)})",
        out,
    )
    out = re.sub(r"\^(\w)", lambda m: _SUPERS.get(m.group(1), "^" + m.group(1)), out)
    out = out.replace("{", "").replace("}", "")            # bỏ ngoặc gom nhóm
    out = out.replace(_LBRACE, "{").replace(_RBRACE, "}")  # trả lại ngoặc tập hợp
    return out.replace("\\", "").strip()                   # bỏ backslash còn sót


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT, size)
    except OSError:
        return ImageFont.load_default()


def render_slide(slide: Slide, out_path: str | Path, *, index: int = 0, total: int = 1) -> Path:
    """Vẽ 1 slide PNG tĩnh 1280x720 (tiện ích/test). Video thật dùng animate.py.
    Validate mọi công thức qua KaTeX trước (sai cú pháp -> KaTeXError)."""
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
