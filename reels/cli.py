"""Command line for the AI short-reel pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reels.pipeline import clip_local, load_topics, make_shorts
from reels.publish import upload_ready
from reels.voice import DEFAULT_VOICES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reels",
        description="Fetch an AI headline, write a short script, voice it, and pack a 9:16 draft for CapCut.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    topics = sub.add_parser("topics", help="Print trending AI headlines")
    topics.add_argument("--limit", type=int, default=8)

    make = sub.add_parser("make", help="Create one or more original shorts")
    make.add_argument("--count", type=int, default=1)
    make.add_argument("--topic", help="Use this headline instead of fetching")
    make.add_argument("--url", default="")
    make.add_argument("--summary", default="")
    make.add_argument("--source", default="")
    make.add_argument("--out", default="output/reels")
    make.add_argument("--voice", default=DEFAULT_VOICES[0])
    make.add_argument("--rate", default="+8%")
    make.add_argument("--no-voice", action="store_true")
    make.add_argument("--no-render", action="store_true")

    clip = sub.add_parser("clip", help="Cut a local video you already own into a 9:16 file")
    clip.add_argument("--video", required=True)
    clip.add_argument("--start", type=float, required=True)
    clip.add_argument("--end", type=float, required=True)
    clip.add_argument("--title", default="Local clip")
    clip.add_argument("--fit", choices=("pad", "fill"), default="pad")
    clip.add_argument("--captions")
    clip.add_argument("--out", default="output/reels")

    publish = sub.add_parser("publish", help="Show the post pack, and upload when --upload is set")
    publish.add_argument("bundle")
    publish.add_argument("--upload", action="store_true")
    publish.add_argument(
        "--platform",
        action="append",
        choices=("youtube", "tiktok", "instagram"),
        help="Repeat to upload one platform. The default is every platform that has a token.",
    )

    args = parser.parse_args(argv)
    if args.command == "topics":
        return _topics(args.limit)
    if args.command == "make":
        return _make(args)
    if args.command == "clip":
        return _clip(args)
    return _publish(args)


def _topics(limit: int) -> int:
    found, notes = load_topics(limit, None, "", "", "")
    for note in notes:
        print(note)
    for topic in found:
        print(f"[{topic.origin}] {topic.title}")
        print(f"  {topic.source}  {topic.url}")
    return 0


def _make(args: argparse.Namespace) -> int:
    found, notes = load_topics(args.count, args.topic, args.url, args.summary, args.source)
    for note in notes:
        print(note)
    made = make_shorts(
        found,
        Path(args.out),
        voice=args.voice,
        rate=args.rate,
        speak=not args.no_voice,
        render=not args.no_render,
    )
    for item in made:
        print(item.directory)
        if item.video:
            print(f"  video: {item.video}")
        print("  next: open EDIT.md, then finish in CapCut or post the draft")
    return 0


def _clip(args: argparse.Namespace) -> int:
    captions = Path(args.captions) if args.captions else None
    made = clip_local(
        Path(args.video),
        Path(args.out),
        start=args.start,
        end=args.end,
        title=args.title,
        fit=args.fit,
        captions=captions,
    )
    print(made.directory)
    if made.video:
        print(f"  video: {made.video}")
    return 0


def _publish(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle)
    manifest = json.loads((bundle / "post" / "manifest.json").read_text(encoding="utf-8"))
    print(bundle / "post" / "youtube.txt")
    print(bundle / "post" / "tiktok.txt")
    print(bundle / "post" / "instagram.txt")
    if not args.upload:
        print("Add --upload after YOUTUBE_ACCESS_TOKEN, TIKTOK_ACCESS_TOKEN, or IG_ACCESS_TOKEN is set.")
        print("YouTube uploads as private. TikTok uploads to your inbox draft.")
        return 0
    results = upload_ready(bundle, args.platform or [])
    if not results:
        print("No upload ran. Set the token for at least one platform and try again.")
        return 1
    print(json.dumps({"uploads": results, "skipped": manifest.get("skipped")}, indent=2))
    return 0
