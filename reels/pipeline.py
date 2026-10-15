"""Assemble a topic, script, voiceover, captions, and CapCut handoff."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reels.captions import Cue, build_ass, even_captions, parse_srt
from reels.publish import write_post_pack
from reels.render import have_ffmpeg, media_duration, pick_font, render_clip, render_draft
from reels.script import Script, build_script, clip_script
from reels.topics import Topic, collect_topics


@dataclass
class Made:
    directory: Path
    video: Path | None
    title: str


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return (slug[:48] or "ai-short").strip("-")


def make_shorts(
    topics: list[Topic],
    out_root: Path,
    *,
    voice: str,
    rate: str = "+8%",
    speak: bool = True,
    render: bool = True,
) -> list[Made]:
    made: list[Made] = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for index, topic in enumerate(topics, start=1):
        directory = out_root / f"{stamp}-{index}-{slugify(topic.title)}"
        directory.mkdir(parents=True, exist_ok=True)
        script = build_script(topic)
        _write_script(directory, script)
        video: Path | None = None
        try:
            if speak:
                video = _speak_and_maybe_render(directory, script, voice, rate, render)
            else:
                _write_template(directory, script, None, [])
        finally:
            write_post_pack(directory, script, video)
            _write_edit_guide(directory, script, video is not None)
        made.append(Made(directory=directory, video=video, title=script.title))
    return made


def clip_local(
    source: Path,
    out_root: Path,
    *,
    start: float,
    end: float,
    title: str,
    fit: str = "pad",
    captions: Path | None = None,
) -> Made:
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required to clip a local video.")
    topic = Topic(title=title, url="", source=source.name, origin="local", score=0, summary="")
    script = clip_script(topic)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = out_root / f"{stamp}-clip-{slugify(title)}"
    directory.mkdir(parents=True, exist_ok=True)
    _write_script(directory, script)
    cues: list[Cue] = []
    if captions is not None:
        cues = parse_srt(captions.read_text(encoding="utf-8"))
        (directory / "captions.srt").write_text(captions.read_text(encoding="utf-8"), encoding="utf-8")
        (directory / "captions.ass").write_text(
            build_ass(cues, title, font=pick_font()),
            encoding="utf-8",
        )
    video = directory / "draft.mp4"
    render_clip(
        source,
        video,
        start,
        end,
        fit=fit,
        ass_path=(directory / "captions.ass") if cues else None,
    )
    _write_template(directory, script, video, cues)
    write_post_pack(directory, script, video)
    _write_edit_guide(directory, script, True, commentary=False)
    return Made(directory=directory, video=video, title=script.title)


def load_topics(count: int, title: str | None, url: str, summary: str, source: str) -> tuple[list[Topic], list[str]]:
    if title:
        return [Topic(title=title, url=url, source=source, origin="manual", score=0, summary=summary)], []
    topics, notes = collect_topics(limit=max(count, 1))
    return topics[:count], notes


def _speak_and_maybe_render(directory: Path, script: Script, voice: str, rate: str, render: bool) -> Path | None:
    from reels.voice import synthesize

    audio = directory / "voiceover.mp3"
    srt = synthesize(script.spoken_lines, audio, voice=voice, rate=rate)
    cues = parse_srt(srt)
    if not cues and have_ffmpeg():
        cues = even_captions(script.spoken_lines, media_duration(audio))
        srt = ""
    if not srt and cues:
        from reels.captions import compose_srt

        srt = compose_srt(cues)
    (directory / "captions.srt").write_text(srt, encoding="utf-8")
    (directory / "captions.ass").write_text(build_ass(cues, script.topic.title, font=pick_font()), encoding="utf-8")
    video: Path | None = None
    if render:
        if not have_ffmpeg():
            _write_template(directory, script, None, cues)
            return None
        video = directory / "draft.mp4"
        render_draft(audio, directory / "captions.ass", video)
    _write_template(directory, script, video, cues)
    return video


def _write_script(directory: Path, script: Script) -> None:
    (directory / "topic.json").write_text(json.dumps(script.topic.to_dict(), indent=2) + "\n", encoding="utf-8")
    (directory / "script.json").write_text(json.dumps(script.to_dict(), indent=2) + "\n", encoding="utf-8")
    (directory / "script.txt").write_text("\n\n".join(script.spoken_lines) + "\n", encoding="utf-8")


def _write_template(directory: Path, script: Script, video: Path | None, cues: list[Cue]) -> None:
    duration = round(cues[-1].end, 2) if cues else None
    template = {
        "version": 1,
        "name": "ai-news-vertical",
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "duration_sec": duration,
        "style": {
            "background": "#0B1020",
            "accent": "#7C5CFF",
            "font": "Inter",
            "caption_size": 68,
            "headline_size": 42,
        },
        "assets": {
            "voiceover": "voiceover.mp3" if (directory / "voiceover.mp3").exists() else None,
            "captions": "captions.srt" if (directory / "captions.srt").exists() else None,
            "draft": video.name if video else None,
        },
        "layers": [
            {"id": "kicker", "type": "text", "text": "TODAY IN AI", "position": "top"},
            {"id": "headline", "type": "text", "text": script.topic.title, "position": "upper"},
            {"id": "captions", "type": "srt", "file": "captions.srt", "position": "lower_middle"},
            {"id": "voice", "type": "audio", "file": "voiceover.mp3"},
            {
                "id": "broll",
                "type": "video",
                "note": "Replace the flat background with footage you have rights to, or apply your CapCut template.",
            },
        ],
    }
    (directory / "template.json").write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")


def _write_edit_guide(directory: Path, script: Script, has_video: bool, commentary: bool = True) -> None:
    if has_video and commentary:
        draft = "draft.mp4 is a 1080x1920 rough cut with the voiceover and captions burned in."
    elif has_video:
        draft = "draft.mp4 is your footage fitted to 1080x1920."
    else:
        draft = "No draft.mp4 yet. Install ffmpeg, then run make again, or edit from the audio and SRT."
    about = (
        "This bundle is original commentary on a public headline. It does not download or reupload someone else's video."
        if commentary
        else "This cut only uses the local file you passed in."
    )
    guide = f"""# Edit this short

{draft}

{about}

## CapCut

1. New project, ratio 9:16.
2. Import `draft.mp4` if you only need light changes. Or import `voiceover.mp3` onto the audio track and put your own B-roll on the video track.
3. Import captions: Text, then Captions, then Import, and choose `captions.srt`.
4. Apply your saved CapCut template. `template.json` lists the text layers: kicker (`TODAY IN AI`), the headline, and the lower captions.
5. Keep the headline inside the top safe area and the captions above the bottom buttons.
6. Export 1080x1920, 30 fps.

## Post

Paste the copy in `post/`:

- `youtube.txt` for the title and description
- `tiktok.txt` for the caption
- `instagram.txt` for the Reel caption

Uploads stay private or in draft until you review them. From the repo root, after the API tokens in `reels/README.md` are set:

```bash
python -m reels publish {directory} --upload
```

Working title: {script.title}
"""
    (directory / "EDIT.md").write_text(guide, encoding="utf-8")
