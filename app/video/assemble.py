"""Ghép slide + giọng đọc thành mp4 bằng ffmpeg (US-18 Scenario 2).

Chia đều thời lượng audio cho các slide (mỗi slide hiển thị trong lúc đọc phần
tương ứng), ghép ảnh + audio, xuất mp4 hợp lệ. Thời lượng phải nằm trong
[video_min_seconds, video_max_seconds]; ngoài khoảng -> AssembleError (không
phát hành video sai độ dài)."""

import subprocess
from pathlib import Path

from app.config import settings


class AssembleError(Exception):
    pass


def _concat_file(slides: list[Path], per_slide: float, tmp: Path) -> Path:
    """File mô tả cho ffmpeg concat demuxer: mỗi ảnh giữ `per_slide` giây."""
    lines = []
    for png in slides:
        lines.append(f"file '{png.resolve()}'")
        lines.append(f"duration {per_slide:.3f}")
    lines.append(f"file '{slides[-1].resolve()}'")  # ảnh cuối lặp lại (yêu cầu của demuxer)
    listing = tmp / "concat.txt"
    listing.write_text("\n".join(lines), encoding="utf-8")
    return listing


def assemble(slides: list[Path], audio_path: str | Path, out_mp4: str | Path,
             *, audio_duration: float) -> float:
    """Trả về thời lượng video. Raise AssembleError nếu ngoài khoảng cho phép
    hoặc ffmpeg lỗi."""
    if not slides:
        raise AssembleError("Không có slide để ghép")
    if not (settings.video_min_seconds <= audio_duration <= settings.video_max_seconds):
        raise AssembleError(
            f"Thời lượng {audio_duration:.1f}s ngoài khoảng "
            f"{settings.video_min_seconds}-{settings.video_max_seconds}s"
        )

    out = Path(out_mp4)
    tmp = out.parent
    per_slide = audio_duration / len(slides)
    listing = _concat_file(slides, per_slide, tmp)

    proc = subprocess.run(
        ["ffmpeg", "-y",
         "-f", "concat", "-safe", "0", "-i", str(listing),
         "-i", str(audio_path),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "25",
         "-c:a", "aac", "-shortest",
         "-vf", "scale=1280:720", str(out)],
        capture_output=True, text=True,
    )
    listing.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise AssembleError(f"ffmpeg ghép lỗi: {proc.stderr[-300:]}")
    return audio_duration
