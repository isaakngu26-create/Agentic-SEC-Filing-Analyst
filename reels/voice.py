"""Neural voiceover via edge-tts, one take per spoken line."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from reels.captions import Cue, compose_srt, parse_srt, readable_captions
from reels.render import have_ffmpeg, media_duration

DEFAULT_VOICES = (
    "en-US-AndrewNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-GuyNeural",
)
_GAP_SECONDS = 0.12


def synthesize(lines: list[str], audio_path: Path, voice: str = DEFAULT_VOICES[0], rate: str = "+8%") -> str:
    import edge_tts

    spoken = [line.strip() for line in lines if line.strip()]
    if not spoken:
        raise ValueError("The script has no spoken lines.")
    voices = (voice,) + tuple(item for item in DEFAULT_VOICES if item != voice)
    last_error: Exception | None = None
    for candidate in voices:
        try:
            if have_ffmpeg():
                srt = _by_line(edge_tts, spoken, audio_path, candidate, rate)
            else:
                srt = asyncio.run(_one_take(edge_tts, " ".join(spoken), audio_path, candidate, rate))
        except Exception as exc:  # The service error type varies; try the next voice.
            last_error = exc
            continue
        if audio_path.exists() and audio_path.stat().st_size > 1000:
            return srt
    if last_error:
        raise RuntimeError(f"Voiceover failed: {last_error}") from last_error
    raise RuntimeError("Voiceover failed before any audio was written.")


def _by_line(edge_tts, lines: list[str], audio_path: Path, voice: str, rate: str) -> str:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    cues: list[Cue] = []
    cursor = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        silence = root / "gap.wav"
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono",
                "-t",
                f"{_GAP_SECONDS}",
                str(silence),
            ]
        )
        parts: list[Path] = []
        for index, line in enumerate(lines):
            mp3 = root / f"{index}.mp3"
            asyncio.run(_write_audio(edge_tts, line, mp3, voice, rate))
            wav = root / f"{index}.wav"
            _run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(wav)])
            duration = media_duration(wav)
            cues.append(Cue(cursor, cursor + duration, line))
            parts.append(wav)
            cursor += duration
            if index != len(lines) - 1:
                parts.append(silence)
                cursor += _GAP_SECONDS
        listing = root / "list.txt"
        listing.write_text("".join(f"file '{path.as_posix()}'\n" for path in parts), encoding="utf-8")
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c:a",
                "libmp3lame",
                "-q:a",
                "4",
                str(audio_path),
            ]
        )
    return compose_srt(readable_captions(cues, max_words=8))


async def _write_audio(edge_tts, text: str, path: Path, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    with path.open("wb") as handle:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
    if not path.exists() or path.stat().st_size < 100:
        raise RuntimeError("The voice service returned empty audio.")


async def _one_take(edge_tts, text: str, audio_path: Path, voice: str, rate: str) -> str:
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="SentenceBoundary")
    submaker = edge_tts.SubMaker()
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    with audio_path.open("wb") as handle:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)
    return compose_srt(readable_captions(parse_srt(submaker.get_srt())))


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-8:]
        raise RuntimeError("ffmpeg failed while building the voiceover:\n" + "\n".join(tail))
