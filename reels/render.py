"""Render a 1080x1920 draft and crop local footage the caller already owns."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def pick_font() -> str:
    if not shutil.which("fc-list"):
        return "Sans"
    for name in ("Inter", "DejaVu Sans", "Noto Sans", "Liberation Sans"):
        result = subprocess.run(["fc-list", name], capture_output=True, text=True, check=False)
        if result.stdout.strip():
            return name
    return "Sans"


def media_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0.1, float(result.stdout.strip()))


def fit_filter(fit: str) -> str:
    if fit == "fill":
        return "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if fit == "pad":
        return "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0B1020"
    raise ValueError("fit must be 'pad' or 'fill'")


def render_draft(audio: Path, ass_path: Path, destination: Path) -> None:
    duration = media_duration(audio) + 0.25
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x0B1020:s=1080x1920:r=30:d={duration:.3f}",
        "-i",
        audio.name,
        "-filter_complex",
        "[0:v]drawbox=x=0:y=0:w=1080:h=16:color=0x7C5CFF:t=fill,subtitles=captions.ass[v]",
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        destination.name,
    ]
    _run(command, cwd=audio.parent)


def render_clip(
    source: Path,
    destination: Path,
    start: float,
    end: float,
    fit: str = "pad",
    ass_path: Path | None = None,
) -> None:
    if end <= start:
        raise ValueError("clip end time must be after the start time")
    filters = fit_filter(fit)
    if ass_path is not None:
        filters += ",subtitles=captions.ass"
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
        "-vf",
        filters,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    _run(command, cwd=destination.parent)


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(tail))
