"""Neural voiceover via edge-tts, plus word-timed captions."""

from __future__ import annotations

import asyncio
from pathlib import Path

from reels.captions import compose_srt, parse_srt, readable_captions

DEFAULT_VOICES = (
    "en-US-AndrewNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-GuyNeural",
)


def synthesize(text: str, audio_path: Path, voice: str = DEFAULT_VOICES[0], rate: str = "+8%") -> str:
    import edge_tts

    voices = (voice,) + tuple(item for item in DEFAULT_VOICES if item != voice)
    last_error: Exception | None = None
    for candidate in voices:
        try:
            srt = asyncio.run(_stream(edge_tts, text, audio_path, candidate, rate))
        except Exception as exc:  # The service error type varies; try the next voice.
            last_error = exc
            continue
        if audio_path.exists() and audio_path.stat().st_size > 1000:
            return srt
    if last_error:
        raise RuntimeError(f"Voiceover failed: {last_error}") from last_error
    raise RuntimeError("Voiceover failed before any audio was written.")


async def _stream(edge_tts, text: str, audio_path: Path, voice: str, rate: str) -> str:
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    submaker = edge_tts.SubMaker()
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    with audio_path.open("wb") as handle:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                submaker.feed(chunk)
    return compose_srt(readable_captions(parse_srt(submaker.get_srt())))
