"""Sinh giọng thuyết minh tiếng Việt cho video (US-18 Scenario 3).

Dev dùng macOS `say` giọng vi_VN ("Linh") -> AIFF -> ffmpeg sang m4a; trả về
thời lượng (giây). Đây là interface có thể thay bằng TTS cloud ở prod mà không
đụng pipeline. Không có công cụ TTS -> raise TTSUnavailable (pipeline chuyển
job FAILED, không đính video hỏng)."""

import shutil
import subprocess
from pathlib import Path

from app.config import settings


class TTSUnavailable(Exception):
    pass


def _duration(path: str | Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def synthesize(text: str, out_path: str | Path, *, voice: str | None = None) -> float:
    """Đọc `text` thành file audio tại out_path (.m4a). Trả về thời lượng giây."""
    if not shutil.which("say"):
        raise TTSUnavailable("Không có công cụ TTS (macOS `say`)")
    voice = voice or settings.video_tts_voice
    out = Path(out_path)
    aiff = out.with_suffix(".aiff")

    say = subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                         capture_output=True, text=True)
    if say.returncode != 0:
        raise TTSUnavailable(f"say lỗi: {say.stderr[:200]}")

    conv = subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-c:a", "aac", str(out)],
                          capture_output=True, text=True)
    aiff.unlink(missing_ok=True)
    if conv.returncode != 0:
        raise TTSUnavailable(f"ffmpeg chuyển audio lỗi: {conv.stderr[-200:]}")
    return _duration(out)
