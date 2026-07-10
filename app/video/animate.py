"""Dựng video hoạt hình KHÔNG tiếng kiểu explainer AI: nền là ẢNH CẢNH do AI
sinh (giáo viên + lớp học), overlay bảng nội dung + công thức + phụ đề sắc nét,
thêm chuyển động zoom nhẹ (Ken Burns). Frame do Pillow vẽ, đẩy thẳng (rawvideo)
vào ffmpeg -> mp4 h264.

Không có ảnh nền (background=None) -> quay về nền gradient + minh hoạ vector
(illustrations.py). Tất định: frame là hàm thuần của (nội dung, chỉ số frame).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.video import illustrations, tts
from app.video.render import katex_validate, latex_to_unicode
from app.video.script import Slide, Storyboard

_W, _H, _FPS = 1280, 720, 25
_SEC_PER_SLIDE = 5.0
_FONT = "/Library/Fonts/Arial Unicode.ttf"

# Logo DTP đóng dấu góc trên-trái mọi frame (thương hiệu). Tải + resize 1 lần.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "web" / "public" / "dtp-logo.png"


def _load_logo(height: int = 56) -> Image.Image | None:
    try:
        logo = Image.open(_LOGO_PATH).convert("RGBA")
    except OSError:
        return None
    w = round(logo.width * height / logo.height)
    return logo.resize((w, height))


_LOGO = _load_logo()

_INK = (34, 45, 70)
_BLUE = (24, 66, 150)
_BLUE2 = (43, 111, 246)
_SUB = (107, 120, 150)

# Vùng "viết lên bảng" — nửa trái khung, nơi ảnh nền cố ý chừa bảng trắng trống
# (xem scene.py). Nội dung vẽ TRỰC TIẾP ở đây như viết tay trên bảng, không còn
# thẻ trắng đục + thanh tiêu đề như slide.
_BOARD_X0, _BOARD_Y0, _BOARD_X1, _BOARD_Y1 = 62, 74, 668, 452


def _font(size: int):
    try:
        return ImageFont.truetype(_FONT, size)
    except OSError:
        return ImageFont.load_default()


def _ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _gradient_bg() -> Image.Image:
    img = Image.new("RGB", (_W, _H), (244, 248, 255))
    top, bot = (238, 244, 255), (250, 252, 255)
    for y in range(_H):
        f = y / _H
        img.paste(tuple(int(top[i] + (bot[i] - top[i]) * f) for i in range(3)), (0, y, _W, y + 1))
    return img


_GRADIENT = _gradient_bg()


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


def _zoom(bg: Image.Image, prog: float) -> Image.Image:
    """Ken Burns: phóng nhẹ 1.0 -> 1.06 theo tiến độ toàn video, crop giữa."""
    scale = 1.0 + 0.06 * max(0.0, min(1.0, prog))
    w, h = round(_W / scale), round(_H / scale)
    left, top = (_W - w) // 2, (_H - h) // 2
    return bg.crop((left, top, left + w, top + h)).resize((_W, _H))


def _subtitle(d, text: str, alpha: float) -> None:
    """Phụ đề canh GIỮA dưới đáy (như ảnh tham chiếu): chữ trắng trên pill tối
    bo tròn, rộng vừa đủ theo nội dung."""
    fnt = _font(26)
    lines = _wrap(d, text, fnt, _W - 360)[:2]
    widths = [d.textlength(l, font=fnt) for l in lines]
    box_w = max(widths) + 72
    bx0 = (_W - box_w) // 2
    bh = 38 * len(lines) + 26
    by1, by0 = _H - 44, _H - 44 - (38 * len(lines) + 26)
    d.rounded_rectangle([bx0, by0, bx0 + box_w, by1], radius=18,
                        fill=(18, 26, 46, int(206 * alpha)))
    cy = by0 + 15
    for line, w in zip(lines, widths):
        d.text(((_W - w) // 2, cy), line, font=fnt, fill=(255, 255, 255, int(255 * alpha)))
        cy += 38


def _slide_frame(slide, local_frame, total_frames, index, total,
                 bg: Image.Image, has_scene: bool, global_prog: float) -> Image.Image:
    prog = local_frame / max(1, total_frames)
    base = _zoom(bg, global_prog) if has_scene else bg.copy()
    img = base.convert("RGBA")
    layer = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    x = _BOARD_X0
    if has_scene:
        # Lớp trắng RẤT mờ chỉ để bảo đảm tương phản chữ trên bảng — đọc như mặt
        # bảng, KHÔNG phải thẻ slide đục. Không có thanh tiêu đề màu.
        d.rounded_rectangle([_BOARD_X0 - 20, _BOARD_Y0 - 20, _BOARD_X1 + 20, _BOARD_Y1 + 20],
                            radius=22, fill=(255, 255, 255, 66))
    else:
        # Nền gradient (không có ảnh cảnh): nền đục để dễ đọc + minh hoạ vector.
        d.rounded_rectangle([_BOARD_X0 - 20, _BOARD_Y0 - 20, _BOARD_X1 + 20, _BOARD_Y1 + 20],
                            radius=22, fill=(255, 255, 255, 255))
        if prog > 0.15:
            illustrations.draw(None, d, 990, 380, _ease((prog - 0.15) / 0.3), local_frame)

    # Tiêu đề: chữ xanh đậm + gạch chân kiểu bút dạ (trượt vào nhẹ), KHÔNG thanh nền.
    head_in = _ease(prog / 0.12) if prog < 0.12 else 1.0
    tal = int(255 * head_in)
    ty = _BOARD_Y0 + int(-6 + 6 * head_in)
    title = slide.tieu_de or "Bài học"
    tf = _font(38)
    d.text((x, ty), title, font=tf, fill=(*_BLUE, tal))
    tw = d.textlength(title, font=tf)
    d.line([x, ty + 52, x + tw, ty + 52], fill=(*_BLUE2, int(220 * head_in)), width=4)
    d.text((_BOARD_X1 - 52, ty + 8), f"{index + 1}/{total}", font=_font(20),
           fill=(*_SUB, tal))

    # Ý chính hiện dần (chấm xanh + chữ mực)
    y = ty + 86
    text_w = _BOARD_X1 - x
    bullets = slide.y_chinh[:3]
    for i, bullet in enumerate(bullets):
        if y > _BOARD_Y1 - 40:
            break
        start = 0.12 + 0.5 * (i / max(1, len(bullets)))
        a = _ease((prog - start) / 0.18) if prog > start else 0.0
        if a <= 0:
            continue
        al = int(255 * a)
        d.ellipse([x + 2, y + 11, x + 14, y + 23], fill=(*_BLUE2, al))
        for line in _wrap(d, bullet, _font(27), text_w - 34):
            d.text((x + 30, y), line, font=_font(27), fill=(*_INK, al))
            y += 39
        y += 14

    # Công thức: bút dạ xanh lớn + gạch nền nhạt (không phải hộp đục)
    for ct in slide.cong_thuc[:1]:
        a = _ease((prog - 0.4) / 0.2) if prog > 0.4 else 0.0
        if a <= 0 or y + 60 > _BOARD_Y1:
            continue
        al = int(255 * a)
        uni = latex_to_unicode(ct)
        ff = _font(44)
        fw = d.textlength(uni, font=ff)
        d.rounded_rectangle([x - 6, y + 44, x + fw + 16, y + 56], radius=5,
                            fill=(*_BLUE2, int(70 * a)))
        d.text((x + 4, y), uni, font=ff, fill=(*_BLUE, al))
        y += 72

    # Phụ đề canh giữa dưới đáy
    if slide.loi_thoai:
        a = _ease((prog - 0.2) / 0.2) if prog > 0.2 else 0.0
        if a > 0:
            _subtitle(d, slide.loi_thoai, a)

    # Logo DTP góc trên-trái (trên nền chip trắng bo tròn cho dễ đọc trên mọi cảnh)
    if _LOGO is not None:
        lw, lh = _LOGO.size
        pad = 12
        d.rounded_rectangle([20, 18, 20 + lw + 2 * pad, 18 + lh + 2 * pad], radius=14,
                            fill=(255, 255, 255, 235))

    final = Image.alpha_composite(img, layer)
    if _LOGO is not None:
        final.alpha_composite(_LOGO, (32, 30))
    return final.convert("RGB")


def _ff(args: list[str]) -> None:
    p = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg lỗi: {p.stderr[-300:]}")


def _slide_durations(storyboard: Storyboard, tmp: Path, sec_per_slide: float
                     ) -> tuple[list[float], list[Path | None]]:
    """Thời lượng mỗi slide theo giọng đọc (nếu có TTS) + file audio từng slide.
    Slide không lời / không TTS -> giữ sec_per_slide, audio None (đệm im lặng)."""
    want = tts.available()
    durations: list[float] = []
    segs: list[Path | None] = []
    for i, s in enumerate(storyboard.slides):
        txt = (s.loi_thoai or "").strip()
        seg: Path | None = None
        if want and txt:
            seg = tmp / f"seg{i}.m4a"
            try:
                dur = tts.synthesize(txt, seg)
            except tts.TTSUnavailable:
                want, seg, dur = False, None, sec_per_slide
            else:
                dur = max(2.5, min(14.0, dur)) + 0.5  # đệm nhẹ cuối câu
        else:
            dur = sec_per_slide
        durations.append(dur)
        segs.append(seg)
    return durations, segs


def _build_audio(segs: list[Path | None], durations: list[float], tmp: Path) -> Path | None:
    """Ghép audio từng slide (đệm im lặng cho đủ đúng thời lượng slide) thành 1
    track. None nếu không slide nào có giọng đọc."""
    if not any(segs):
        return None
    parts = []
    for i, (seg, dur) in enumerate(zip(segs, durations)):
        pad = tmp / f"pad{i}.m4a"
        if seg is not None:  # giọng đọc + đệm im lặng cho đủ dur
            _ff(["-i", str(seg), "-af", "apad", "-t", f"{dur:.3f}", "-c:a", "aac", str(pad)])
        else:                # slide không lời -> im lặng đúng dur
            _ff(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                 "-t", f"{dur:.3f}", "-c:a", "aac", str(pad)])
        parts.append(pad)
    listing = tmp / "audio_list.txt"
    listing.write_text("\n".join(f"file '{p.resolve()}'" for p in parts), encoding="utf-8")
    out = tmp / "audio.m4a"
    _ff(["-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "aac", str(out)])
    return out


def render_storyboard(storyboard: Storyboard, out_mp4: str | Path,
                      *, concept_slug: str | None = None,
                      background: Image.Image | None = None,
                      sec_per_slide: float = _SEC_PER_SLIDE) -> float:
    """Sinh mp4 CÓ TIẾNG (thuyết minh tiếng Việt) — mỗi slide hiển thị đúng bằng
    thời lượng giọng đọc của nó. Không có TTS -> video câm, mỗi slide
    sec_per_slide. `background` là ảnh cảnh AI (1280x720) — None thì nền gradient
    + minh hoạ vector. Trả về thời lượng (giây)."""
    for s in storyboard.slides:
        for ct in s.cong_thuc:
            katex_validate(ct)

    has_scene = background is not None
    bg = background if has_scene else _GRADIENT

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        durations, segs = _slide_durations(storyboard, tmp, sec_per_slide)
        frame_counts = [max(1, round(d * _FPS)) for d in durations]
        total_frames_all = sum(frame_counts)

        silent = tmp / "silent.mp4"
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
             "-video_size", f"{_W}x{_H}", "-framerate", str(_FPS), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(silent)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None
        try:
            total = len(storyboard.slides)
            done = 0
            for idx, slide in enumerate(storyboard.slides):
                n = frame_counts[idx]
                for f in range(n):
                    gp = done / max(1, total_frames_all)
                    frame = _slide_frame(slide, f, n, idx, total, bg, has_scene, gp)
                    proc.stdin.write(frame.tobytes())
                    done += 1
        finally:
            proc.stdin.close()
        err = proc.stderr.read().decode()[-300:] if proc.stderr else ""
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg dựng video lỗi: {err}")

        audio = _build_audio(segs, durations, tmp)
        if audio is None:  # câm
            shutil.copyfile(silent, out_mp4)
        else:              # ghép tiếng
            _ff(["-i", str(silent), "-i", str(audio), "-c:v", "copy",
                 "-c:a", "aac", "-shortest", str(out_mp4)])

    return float(sum(durations))
