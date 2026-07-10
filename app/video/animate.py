"""Dựng video hoạt hình KHÔNG tiếng (kiểu explainer AI): mỗi slide có tiêu đề,
ý chính hiện dần, công thức, minh hoạ chuyển động và phụ đề (lời thoại thành
chữ vì không có audio). Frame do Pillow vẽ, đẩy thẳng (rawvideo) vào ffmpeg qua
stdin -> mp4 h264 (không cần ghi hàng trăm PNG ra đĩa, không cần TTS/host tool).

Tất định: frame là hàm thuần của (nội dung, chỉ số frame) — không dùng random.
"""

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.video import illustrations
from app.video.render import katex_validate, latex_to_unicode
from app.video.script import Slide, Storyboard

_W, _H, _FPS = 1280, 720, 25
_SEC_PER_SLIDE = 5.0
_FONT = "/Library/Fonts/Arial Unicode.ttf"

_INK = (28, 39, 66)
_BLUE = (27, 79, 191)
_BLUE2 = (43, 111, 246)
_SUB = (107, 120, 150)


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(_FONT, size)
    except OSError:
        return ImageFont.load_default()


def _ease(t: float) -> float:
    """easeOutCubic — chuyển động mượt, chậm dần."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _bg() -> Image.Image:
    """Nền gradient xanh nhạt dựng 1 lần, tái dùng cho mọi frame."""
    img = Image.new("RGB", (_W, _H), (244, 248, 255))
    top, bot = (238, 244, 255), (250, 252, 255)
    for y in range(_H):
        f = y / _H
        img.paste(
            tuple(int(top[i] + (bot[i] - top[i]) * f) for i in range(3)),
            (0, y, _W, y + 1),
        )
    return img


_BG_BASE = _bg()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _slide_frame(slide: Slide, local_frame: int, total_frames: int,
                 index: int, total: int, concept_slug: str | None) -> Image.Image:
    img = _BG_BASE.copy()
    d = ImageDraw.Draw(img)
    prog = local_frame / max(1, total_frames)

    # Header trượt vào ~0.4s đầu
    head_in = _ease(prog / 0.12) if prog < 0.12 else 1.0
    hx = int(-40 + 40 * head_in)
    d.rounded_rectangle([40 + hx, 44, _W - 40 + hx, 128], radius=18, fill=_BLUE)
    d.text((72 + hx, 66), slide.tieu_de or "Bài học", font=_font(38), fill=(255, 255, 255))
    d.text((_W - 150, 74), f"{index + 1}/{total}", font=_font(26), fill=(206, 224, 255))

    # Cột trái: tối đa 3 ý chính, hiện dần từng dòng (giữ chỗ cho phụ đề dưới).
    left_w = 690
    y = 200
    _Y_MAX = _H - 150  # không cho nội dung tràn vào vùng phụ đề
    reveal_span = 0.62
    bullets = slide.y_chinh[:3]
    for i, bullet in enumerate(bullets):
        if y > _Y_MAX:
            break
        start = 0.12 + reveal_span * (i / max(1, len(bullets)))
        a = _ease((prog - start) / 0.18) if prog > start else 0.0
        if a <= 0:
            continue
        dx = int((1 - a) * 24)
        col = tuple(int(255 + (_INK[j] - 255) * a) for j in range(3))
        d.ellipse([64 + dx, y + 12, 78 + dx, y + 26], fill=tuple(int(255 + (_BLUE2[j] - 255) * a) for j in range(3)))
        for line in _wrap(d, bullet, _font(30), left_w - 60):
            d.text((96 + dx, y), line, font=_font(30), fill=col)
            y += 44
        y += 20

    # Công thức: chỉ 1 khung, và chỉ khi còn chỗ (không đè phụ đề).
    for ct in slide.cong_thuc[:1]:
        a = _ease((prog - 0.4) / 0.2) if prog > 0.4 else 0.0
        if a <= 0 or y + 78 > _Y_MAX:
            continue
        d.rounded_rectangle([64, y + 6, left_w, y + 78], radius=12, fill=(232, 240, 255))
        d.text((88, y + 22), latex_to_unicode(ct), font=_font(40), fill=_BLUE)
        y += 96

    # Cột phải: minh hoạ động THEO khái niệm (hiện sau ~0.15 prog)
    if prog > 0.15:
        illustrations.draw(concept_slug, d, 990, 380, _ease((prog - 0.15) / 0.3), local_frame)

    # Phụ đề (lời thoại -> chữ, vì không có tiếng) hiện cuối slide
    if slide.loi_thoai:
        a = _ease((prog - 0.25) / 0.2) if prog > 0.25 else 0.0
        if a > 0:
            d.rounded_rectangle([40, _H - 118, _W - 40, _H - 40], radius=14,
                                fill=(255, 255, 255))
            cy = _H - 104
            for line in _wrap(d, slide.loi_thoai, _font(26), _W - 130)[:2]:
                col = tuple(int(255 + (_SUB[j] - 255) * a) for j in range(3))
                d.text((72, cy), line, font=_font(26), fill=col)
                cy += 34
    return img


def render_storyboard(storyboard: Storyboard, out_mp4: str | Path,
                      *, concept_slug: str | None = None,
                      sec_per_slide: float = _SEC_PER_SLIDE) -> float:
    """Sinh mp4 câm từ storyboard. Trả về thời lượng (giây). Validate mọi công
    thức qua KaTeX trước (sai cú pháp -> KaTeXError, không tạo video lỗi)."""
    for s in storyboard.slides:
        for ct in s.cong_thuc:
            katex_validate(ct)

    frames_per_slide = int(sec_per_slide * _FPS)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", f"{_W}x{_H}", "-framerate", str(_FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(out_mp4)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    try:
        total = len(storyboard.slides)
        for idx, slide in enumerate(storyboard.slides):
            for f in range(frames_per_slide):
                frame = _slide_frame(slide, f, frames_per_slide, idx, total, concept_slug)
                proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    err = proc.stderr.read().decode()[-300:] if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg dựng video lỗi: {err}")
    return len(storyboard.slides) * sec_per_slide
