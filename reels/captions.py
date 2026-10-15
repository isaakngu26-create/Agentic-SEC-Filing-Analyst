"""SRT and ASS captions sized for a 9:16 short."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Cue:
    start: float
    end: float
    text: str


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def format_ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def parse_srt(srt: str) -> list[Cue]:
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", srt.strip())
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timing = lines[1] if "-->" in lines[1] else lines[0]
        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        if "-->" not in timing or not text_lines:
            continue
        start_raw, end_raw = [part.strip() for part in timing.split("-->", 1)]
        cues.append(Cue(_timestamp(start_raw), _timestamp(end_raw), " ".join(text_lines).strip()))
    return cues


def _timestamp(value: str) -> float:
    value = value.replace(".", ",")
    clock, millis = value.split(",")
    hours, minutes, seconds = [int(part) for part in clock.split(":")]
    return hours * 3600 + minutes * 60 + seconds + int(millis) / 1000


def compose_srt(cues: list[Cue]) -> str:
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n{format_srt_time(cue.start)} --> {format_srt_time(cue.end)}\n{cue.text.strip()}\n"
        )
    return "\n".join(blocks).strip() + ("\n" if blocks else "")


def readable_captions(cues: list[Cue], max_words: int = 6) -> list[Cue]:
    if not cues:
        return []
    average = sum(len(cue.text.split()) for cue in cues) / len(cues)
    if average < 2:
        return _group_words(cues, max_words)
    return _split_long(cues, max_words)


def _group_words(cues: list[Cue], max_words: int) -> list[Cue]:
    grouped: list[Cue] = []
    bucket: list[Cue] = []

    def flush() -> None:
        if not bucket:
            return
        text = " ".join(cue.text.strip() for cue in bucket).strip()
        grouped.append(Cue(bucket[0].start, max(bucket[-1].end, bucket[0].start + 0.2), text))
        bucket.clear()

    for cue in cues:
        if bucket and len(" ".join(item.text for item in bucket).split()) >= max_words:
            flush()
        bucket.append(Cue(cue.start, cue.end, cue.text.strip()))
        if cue.text.strip().endswith((".", "!", "?")):
            flush()
    flush()
    return [cue for cue in grouped if cue.text]


def _split_long(cues: list[Cue], max_words: int) -> list[Cue]:
    pieces: list[Cue] = []
    for cue in cues:
        words = cue.text.split()
        if len(words) <= max_words:
            pieces.append(Cue(cue.start, cue.end, cue.text.strip()))
            continue
        span = max(cue.end - cue.start, 0.2)
        for offset in range(0, len(words), max_words):
            chunk = words[offset : offset + max_words]
            start = cue.start + span * (offset / len(words))
            end = cue.start + span * ((offset + len(chunk)) / len(words))
            pieces.append(Cue(start, max(end, start + 0.2), " ".join(chunk)))
    return pieces


def even_captions(sentences: list[str], duration: float) -> list[Cue]:
    lines = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not lines:
        return []
    duration = max(duration, len(lines) * 0.8)
    step = duration / len(lines)
    return [Cue(index * step, (index + 1) * step, line) for index, line in enumerate(lines)]


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def wrap_ass(text: str, width: int = 28, max_lines: int = 3) -> str:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join([*current, word])
        if current and len(trial) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\\N".join(ass_escape(line) for line in lines[:max_lines])


def build_ass(cues: list[Cue], headline: str, font: str = "Inter") -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},68,&H00FFFFFF,&H000000FF,&H00101010,&H64000000,-1,0,0,0,100,100,0,0,1,6,0,2,90,90,520,1
Style: Headline,{font},42,&H00FFFFFF,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,8,80,80,230,1
Style: Kicker,{font},30,&H00E4D4FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,8,80,80,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    end = max((cue.end for cue in cues), default=3.0)
    events = [
        f"Dialogue: 0,{format_ass_time(0)},{format_ass_time(end)},Kicker,,0,0,0,,TODAY IN AI",
        f"Dialogue: 0,{format_ass_time(0)},{format_ass_time(end)},Headline,,0,0,0,,{wrap_ass(headline, 32, 3)}",
    ]
    for cue in cues:
        events.append(
            f"Dialogue: 0,{format_ass_time(cue.start)},{format_ass_time(cue.end)},Caption,,0,0,0,,{ass_escape(cue.text)}"
        )
    return header + "\n".join(events) + "\n"
