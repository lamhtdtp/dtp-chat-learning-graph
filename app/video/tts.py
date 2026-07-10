"""Sinh giọng thuyết minh tiếng Việt cho video (US-18 Scenario 3).

Giọng CHÍNH: Gemini TTS qua VNGCloud (POST /v1/speech/tts, định dạng Gemini
native) — trả PCM s16le 24kHz mono base64, ffmpeg đóng sang m4a. Không phụ thuộc
máy (chạy được cả trong container). Dự phòng: macOS `say` giọng "Linh" nếu cloud
lỗi. Không có cả hai -> raise TTSUnavailable (pipeline lùi về video CÂM).
"""

import base64
import shutil
import subprocess
from pathlib import Path

import httpx

from app.config import settings


class TTSUnavailable(Exception):
    pass


def available() -> bool:
    # Có ffmpeg là đủ cho đường cloud; `say` chỉ để dự phòng.
    return shutil.which("ffmpeg") is not None


def duration(path: str | Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _cloud_pcm(text: str, voice: str) -> bytes:
    """Gọi Gemini TTS (VNGCloud) -> PCM thô (s16le, 24000Hz, mono). Style đọc đưa
    vào prompt (Gemini TTS điều giọng theo mô tả tự nhiên)."""
    url = settings.ai_platform_base_url.rstrip("/") + "/v1/speech/tts"
    prompt = f"{settings.video_tts_style}: {text}" if settings.video_tts_style else text
    body = {
        "model": settings.gemini_tts_model,
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1,
            "responseModalities": ["audio"],
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": voice}}},
        },
    }
    r = httpx.post(url, headers={"Authorization": f"Bearer {settings.ai_platform_api_key}"},
                   json=body, timeout=90)
    r.raise_for_status()
    data = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    return base64.b64decode(data)


def _pcm_to_m4a(pcm: bytes, out: Path) -> float:
    raw = out.with_suffix(".pcm")
    raw.write_bytes(pcm)
    conv = subprocess.run(
        ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw),
         "-af", "dynaudnorm=g=5", "-c:a", "aac", str(out)],
        capture_output=True, text=True,
    )
    raw.unlink(missing_ok=True)
    if conv.returncode != 0:
        raise TTSUnavailable(f"ffmpeg đóng audio lỗi: {conv.stderr[-200:]}")
    return duration(out)


# Làm ấm/mượt giọng `say` dự phòng (vốn hơi khô).
_WARM_FILTER = "highpass=f=85,lowpass=f=8000,aecho=0.8:0.85:60:0.18,dynaudnorm=g=5"


def _say_m4a(text: str, out: Path) -> float:
    if not shutil.which("say"):
        raise TTSUnavailable("Không có TTS cloud lẫn macOS `say`")
    aiff = out.with_suffix(".aiff")
    say = subprocess.run(["say", "-v", settings.video_tts_voice, "-r", str(settings.video_tts_rate),
                          "-o", str(aiff), text], capture_output=True, text=True)
    if say.returncode != 0:
        raise TTSUnavailable(f"say lỗi: {say.stderr[:200]}")
    conv = subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-af", _WARM_FILTER, "-c:a", "aac", str(out)],
        capture_output=True, text=True,
    )
    aiff.unlink(missing_ok=True)
    if conv.returncode != 0:
        raise TTSUnavailable(f"ffmpeg chuyển audio lỗi: {conv.stderr[-200:]}")
    return duration(out)


def synthesize(text: str, out_path: str | Path, *, voice: str | None = None) -> float:
    """Đọc `text` thành file audio (.m4a). Ưu tiên Gemini TTS cloud; lỗi -> `say`.
    Trả về thời lượng giây."""
    out = Path(out_path)
    try:
        pcm = _cloud_pcm(text, voice or settings.video_tts_voice_cloud)
        return _pcm_to_m4a(pcm, out)
    except (httpx.HTTPError, KeyError, ValueError) as cloud_err:
        try:
            return _say_m4a(text, out)
        except TTSUnavailable:
            raise TTSUnavailable(f"TTS cloud lỗi ({str(cloud_err)[:120]}) và không có `say`")
