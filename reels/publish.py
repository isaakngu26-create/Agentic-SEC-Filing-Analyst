"""Platform captions, plus optional private/draft uploads when tokens exist."""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from reels.script import Script


def _tags(script: Script, extra: list[str] | None = None) -> list[str]:
    seen: list[str] = []
    for tag in [*script.hashtags, *(extra or [])]:
        clean = tag.lstrip("#").replace(" ", "")
        if clean and clean.casefold() not in {item.casefold() for item in seen}:
            seen.append(clean)
    return seen


def _hashline(tags: list[str]) -> str:
    return " ".join(f"#{tag}" for tag in tags)


def youtube_metadata(script: Script, privacy: str = "private") -> dict:
    source = f"\n\nSource: {script.topic.url}" if script.topic.url else ""
    description = script.spoken + source + "\n\n" + _hashline(_tags(script))
    return {
        "snippet": {
            "title": script.title[:100],
            "description": description[:4900],
            "tags": _tags(script)[:15],
            "categoryId": "28",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }


def tiktok_caption(script: Script) -> str:
    link = f"\n{script.topic.url}" if script.topic.url else ""
    caption = f"{script.hook}\n\n{script.lines[0]}{link}\n\n" + _hashline(_tags(script, ["techtok"]))
    return caption[:2200]


def instagram_caption(script: Script) -> str:
    body = "\n\n".join(script.spoken_lines[:4])
    link = f"\n\n{script.topic.url}" if script.topic.url else ""
    caption = body + link + "\n.\n.\n" + _hashline(_tags(script, ["Reels"]))
    return caption[:2200]


def tiktok_source_info(video_size: int) -> dict:
    ten_mb = 10 * 1024 * 1024
    five_mb = 5 * 1024 * 1024
    if video_size <= five_mb:
        chunk = video_size
        count = 1
    else:
        chunk = min(ten_mb, video_size)
        count = math.ceil(video_size / chunk)
    return {
        "source": "FILE_UPLOAD",
        "video_size": video_size,
        "chunk_size": chunk,
        "total_chunk_count": count,
    }


def write_post_pack(directory: Path, script: Script, video: Path | None) -> Path:
    post_dir = directory / "post"
    post_dir.mkdir(parents=True, exist_ok=True)
    youtube = youtube_metadata(script)
    (post_dir / "youtube.txt").write_text(
        youtube["snippet"]["title"] + "\n\n" + youtube["snippet"]["description"] + "\n",
        encoding="utf-8",
    )
    (post_dir / "tiktok.txt").write_text(tiktok_caption(script) + "\n", encoding="utf-8")
    (post_dir / "instagram.txt").write_text(instagram_caption(script) + "\n", encoding="utf-8")
    manifest = {
        "video": video.name if video else None,
        "privacy": {
            "youtube": "private",
            "tiktok": "inbox draft",
            "instagram": "reel container on your professional account",
        },
        "youtube": youtube,
        "tiktok": {"caption": tiktok_caption(script)},
        "instagram": {"caption": instagram_caption(script)},
        "uploads": {},
    }
    path = post_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _request(url: str, data: bytes | None, headers: dict, method: str) -> tuple[int, dict, str]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
            header = response.headers.get("Location", "")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        safe = urllib.parse.urlsplit(url)
        safe_url = urllib.parse.urlunsplit((safe.scheme, safe.netloc, safe.path, "", ""))
        raise RuntimeError(f"{method} {safe_url} failed ({exc.code}): {raw[:500]}") from exc
    payload: dict = {}
    if raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            payload = {}
    if header:
        payload.setdefault("location", header)
    return status, payload, header


def upload_youtube(video: Path, script: Script, token: str, privacy: str = "private") -> str:
    metadata = json.dumps(youtube_metadata(script, privacy=privacy)).encode()
    size = video.stat().st_size
    status, _payload, location = _request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        metadata,
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        "POST",
    )
    if not location:
        raise RuntimeError(f"YouTube did not return an upload URL (status {status}).")
    _status, body, _location = _request(
        location,
        video.read_bytes(),
        {"Authorization": f"Bearer {token}", "Content-Type": "video/mp4", "Content-Length": str(size)},
        "PUT",
    )
    video_id = str(body.get("id") or "")
    if not video_id:
        raise RuntimeError(f"YouTube upload finished without a video id: {body}")
    return f"https://studio.youtube.com/video/{video_id}/edit"


def upload_tiktok_inbox(video: Path, token: str) -> str:
    size = video.stat().st_size
    _status, body, _location = _request(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        json.dumps({"source_info": tiktok_source_info(size)}).encode(),
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        "POST",
    )
    data = body.get("data") or {}
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")
    error = body.get("error") or {}
    if error.get("code") not in (None, "ok", ""):
        raise RuntimeError(f"TikTok init failed: {error}")
    if not upload_url:
        raise RuntimeError(f"TikTok did not return an upload URL: {body}")
    _request(
        upload_url,
        video.read_bytes(),
        {
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        },
        "PUT",
    )
    return str(publish_id or "tiktok-inbox")


def upload_instagram_reel(video: Path, script: Script, token: str, user_id: str) -> str:
    version = os.environ.get("IG_GRAPH_VERSION", "v21.0")
    query = urllib.parse.urlencode(
        {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": instagram_caption(script),
            "access_token": token,
        }
    )
    start_url = f"https://graph.facebook.com/{version}/{user_id}/media?{query}"
    _status, body, _location = _request(start_url, b"", {"Authorization": f"OAuth {token}"}, "POST")
    creation_id = str(body.get("id") or "")
    upload_uri = str(body.get("uri") or "")
    if not creation_id or not upload_uri:
        raise RuntimeError(f"Instagram did not start a reel upload: {body}")
    size = video.stat().st_size
    _request(
        upload_uri,
        video.read_bytes(),
        {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(size),
            "Content-Type": "application/octet-stream",
        },
        "POST",
    )
    publish_url = f"https://graph.facebook.com/{version}/{user_id}/media_publish"
    _status, published, _location = _request(
        publish_url,
        json.dumps({"creation_id": creation_id, "access_token": token}).encode(),
        {"Content-Type": "application/json"},
        "POST",
    )
    media_id = str(published.get("id") or creation_id)
    return media_id


def upload_ready(directory: Path, platforms: list[str]) -> dict[str, str]:
    manifest_path = directory / "post" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    video_name = manifest.get("video")
    if not video_name:
        raise RuntimeError("This bundle has no draft.mp4 yet. Render the short before uploading.")
    video = directory / video_name
    script_payload = json.loads((directory / "script.json").read_text(encoding="utf-8"))
    topic = script_payload["topic"]
    from reels.topics import Topic

    script = Script(
        title=script_payload["title"],
        category=script_payload["category"],
        hook=script_payload["hook"],
        lines=script_payload["lines"],
        hashtags=script_payload["hashtags"],
        topic=Topic(**topic),
    )
    results: dict[str, str] = {}
    selected = platforms or ["youtube", "tiktok", "instagram"]
    if "youtube" in selected and os.environ.get("YOUTUBE_ACCESS_TOKEN"):
        results["youtube"] = upload_youtube(video, script, os.environ["YOUTUBE_ACCESS_TOKEN"])
    if "tiktok" in selected and os.environ.get("TIKTOK_ACCESS_TOKEN"):
        results["tiktok"] = upload_tiktok_inbox(video, os.environ["TIKTOK_ACCESS_TOKEN"])
    if "instagram" in selected and os.environ.get("IG_ACCESS_TOKEN") and os.environ.get("IG_USER_ID"):
        results["instagram"] = upload_instagram_reel(
            video, script, os.environ["IG_ACCESS_TOKEN"], os.environ["IG_USER_ID"]
        )
    missing = [name for name in selected if name not in results]
    manifest["uploads"] = results
    manifest["skipped"] = missing
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return results
