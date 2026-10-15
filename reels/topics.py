"""Pull public AI headlines from Google News, Hacker News, and Reddit."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

USER_AGENT = "ai-short-reels/1.0"
GOOGLE_NEWS = (
    "https://news.google.com/rss/search?q="
    + urllib.parse.quote("artificial intelligence OR OpenAI OR LLM OR Anthropic when:2d")
    + "&hl=en-US&gl=US&ceid=US:en"
)


def hacker_news_url() -> str:
    since = int(time.time()) - 3 * 24 * 3600
    filters = urllib.parse.quote(f"created_at_i>{since},points>40")
    return (
        "https://hn.algolia.com/api/v1/search?query=AI&tags=story&hitsPerPage=25&numericFilters="
        + filters
    )
REDDIT_URLS = (
    "https://www.reddit.com/r/MachineLearning/hot.json?limit=15",
    "https://www.reddit.com/r/artificial/hot.json?limit=15",
    "https://www.reddit.com/r/LocalLLaMA/hot.json?limit=15",
)

_PHRASES = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "generative ai",
    "gen ai",
    "foundation model",
    "large language",
    "openai",
    "anthropic",
    "chatgpt",
    "deepseek",
    "hugging face",
    "midjourney",
    "perplexity",
    "computer use",
)
_SHORT = re.compile(r"\b(ai|a\.i\.|llm|gpt|llama|claude|gemini|grok|sora|nvidia)\b", re.I)


@dataclass
class Topic:
    title: str
    url: str
    source: str
    origin: str
    score: float
    summary: str = ""
    published: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(text: str, limit: int = 180) -> str:
    text = strip_html(text)
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if len(sentence) > limit:
        trimmed = sentence[:limit].rsplit(" ", 1)[0]
        sentence = (trimmed or sentence[:limit]).rstrip(" ,;:") + "…"
    return sentence


def is_ai_topic(text: str) -> bool:
    lowered = text.casefold()
    if any(phrase in lowered for phrase in _PHRASES):
        return True
    return _SHORT.search(text) is not None


def _host(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    return host


def _fetch(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_google_news_xml(xml_bytes: bytes) -> list[Topic]:
    root = ET.fromstring(xml_bytes)
    topics: list[Topic] = []
    for index, item in enumerate(root.findall("./channel/item")):
        raw_title = strip_html(item.findtext("title") or "")
        source_el = item.find("source")
        publisher = strip_html(source_el.text or "") if source_el is not None else ""
        title = raw_title
        if publisher and raw_title.endswith(" - " + publisher):
            title = raw_title[: -(len(publisher) + 3)].strip()
        link = (item.findtext("link") or "").strip()
        summary = first_sentence(item.findtext("description") or "")
        if not title:
            continue
        topics.append(
            Topic(
                title=title,
                url=link,
                source=publisher or _host(link) or "Google News",
                origin="google-news",
                score=float(70 - index),
                summary=summary,
                published=(item.findtext("pubDate") or "").strip(),
            )
        )
    return topics


def parse_hn_hits(hits: list[dict]) -> list[Topic]:
    topics: list[Topic] = []
    for hit in hits:
        title = strip_html(str(hit.get("title") or ""))
        if not title:
            continue
        url = str(hit.get("url") or "")
        if not url and hit.get("objectID"):
            url = f"https://news.ycombinator.com/item?id={hit['objectID']}"
        topics.append(
            Topic(
                title=title,
                url=url,
                source=_host(url) or "Hacker News",
                origin="hacker-news",
                score=float(hit.get("points") or 0),
                summary="",
                published=str(hit.get("created_at") or ""),
            )
        )
    return topics


def parse_reddit_listing(payload: dict, origin: str = "reddit") -> list[Topic]:
    children = payload.get("data", {}).get("children", [])
    topics: list[Topic] = []
    for child in children:
        data = child.get("data") or {}
        if data.get("stickied") or data.get("over_18"):
            continue
        title = strip_html(str(data.get("title") or ""))
        if not title:
            continue
        permalink = str(data.get("permalink") or "")
        external = str(data.get("url_overridden_by_dest") or data.get("url") or "")
        url = external or ("https://www.reddit.com" + permalink if permalink else "")
        subreddit = str(data.get("subreddit") or "reddit")
        summary = first_sentence(str(data.get("selftext") or ""))
        topics.append(
            Topic(
                title=title,
                url=url,
                source=f"r/{subreddit}",
                origin=origin,
                score=float(data.get("ups") or 0),
                summary=summary,
                published=str(data.get("created_utc") or ""),
            )
        )
    return topics


def _safe_fetch(label: str, url: str, notes: list[str]) -> bytes | None:
    try:
        return _fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        notes.append(f"{label} unavailable: {exc.__class__.__name__}")
        return None


def _normalize(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def dedupe(topics: list[Topic]) -> list[Topic]:
    seen: set[str] = set()
    unique: list[Topic] = []
    for topic in topics:
        key = _normalize(topic.title)[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(topic)
    return unique


def trend_score(topic: Topic) -> float:
    text = f"{topic.title} {topic.summary}".casefold()
    score = float(topic.score)
    if topic.origin == "google-news":
        # RSS order is not engagement, so keep it below stories with real points.
        score *= 0.35
    if any(term in text for term in ("openai", "anthropic", "chatgpt", "gemini", "claude", "nvidia", "deepseek", "llm", "gpt")):
        score += 25
    if any(term in text for term in ("phenotyp", "curriculum", "city business", "discusses", "lecture", "students")):
        score -= 35
    return score


def rank_topics(topics: list[Topic], limit: int) -> list[Topic]:
    ranked = dedupe(topics)
    ranked.sort(key=trend_score, reverse=True)
    return ranked[:limit]


def mix_sources(topics: list[Topic], limit: int) -> list[Topic]:
    grouped: dict[str, list[Topic]] = {}
    for topic in topics:
        grouped.setdefault(topic.origin, []).append(topic)
    for group in grouped.values():
        group.sort(key=lambda item: item.score, reverse=True)
    order = [origin for origin in ("google-news", "hacker-news", "reddit") if grouped.get(origin)]
    order += [origin for origin in grouped if origin not in order]
    mixed: list[Topic] = []
    while len(mixed) < limit and any(grouped.get(origin) for origin in order):
        for origin in order:
            bucket = grouped.get(origin) or []
            if bucket and len(mixed) < limit:
                mixed.append(bucket.pop(0))
    return mixed


def collect_topics(limit: int = 8) -> tuple[list[Topic], list[str]]:
    notes: list[str] = []
    found: list[Topic] = []

    google = _safe_fetch("Google News", GOOGLE_NEWS, notes)
    if google:
        found.extend(parse_google_news_xml(google))

    hn = _safe_fetch("Hacker News", hacker_news_url(), notes)
    if hn:
        try:
            payload = json.loads(hn.decode("utf-8"))
            found.extend(parse_hn_hits(payload.get("hits") or []))
        except json.JSONDecodeError:
            notes.append("Hacker News returned invalid JSON")

    for url in REDDIT_URLS:
        reddit = _safe_fetch("Reddit", url, notes)
        if not reddit:
            continue
        try:
            found.extend(parse_reddit_listing(json.loads(reddit.decode("utf-8"))))
        except json.JSONDecodeError:
            notes.append("Reddit returned invalid JSON")

    ai_topics = [topic for topic in found if is_ai_topic(f"{topic.title} {topic.summary}")]
    chosen = dedupe(ai_topics or found)
    if not chosen:
        raise RuntimeError("No trending AI topics came back. Check your network and run again.")
    if not ai_topics:
        notes.append("Keyword filter kept nothing, so the raw headlines were used.")
    return rank_topics(chosen, limit), notes
