"""Turn a headline into a short spoken script without inventing facts."""

from __future__ import annotations

import json
import os
import re
import urllib.request
import zlib
from dataclasses import asdict, dataclass

from reels.topics import Topic, first_sentence

_HOOKS = {
    "launch": (
        "A new AI release just dropped, and it is worth thirty seconds.",
        "Builders, this AI launch is the one to actually look at.",
    ),
    "research": (
        "A new AI finding just landed. Here is the part worth keeping.",
        "There is a new AI result today, and the headline is not the whole story.",
    ),
    "policy": (
        "AI rules just moved. If you build or post with these tools, listen up.",
        "A new AI policy story is moving, and it is more practical than it sounds.",
    ),
    "news": (
        "Here is the AI story moving today, in plain language.",
        "Thirty seconds on the AI headline people are passing around.",
    ),
}
_WHY = {
    "launch": "What matters is not the announcement itself. It is whether this saves you time on real work this week.",
    "research": "Treat the headline as a claim, not a conclusion. Read the source before you change how you work.",
    "policy": "The practical move is to see what actually changed, then adjust how you ship.",
    "news": "The useful question is simple. Does this change a tool you already use, or is it just noise?",
}


@dataclass
class Script:
    title: str
    category: str
    hook: str
    lines: list[str]
    hashtags: list[str]
    topic: Topic

    @property
    def spoken_lines(self) -> list[str]:
        return [self.hook, *self.lines]

    @property
    def spoken(self) -> str:
        return " ".join(self.spoken_lines)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["spoken"] = self.spoken
        return payload


def classify(title: str) -> str:
    text = title.casefold()
    if any(word in text for word in ("launch", "release", "releases", "ships", "unveils", "introduces", "announces")):
        return "launch"
    if any(word in text for word in ("study", "paper", "research", "finds", "researchers")):
        return "research"
    if any(word in text for word in ("ban", "law", "regulat", "lawsuit", "sues", "bill", "act")):
        return "policy"
    return "news"


def _pick(options: tuple[str, ...], key: str) -> str:
    return options[zlib.crc32(key.encode()) % len(options)]


def _spoken_parts(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _ends(sentence: str) -> str:
    sentence = sentence.strip()
    if not sentence:
        return ""
    if sentence[-1] not in ".!?":
        sentence += "."
    return sentence


def _youtube_title(headline: str) -> str:
    suffix = " #Shorts"
    base = re.sub(r"\s+", " ", headline).strip()
    if len(base) + len(suffix) <= 100:
        return base + suffix
    return base[:100].rstrip()


def template_script(topic: Topic) -> Script:
    headline = re.sub(r"\s+", " ", topic.title).strip()
    category = classify(headline)
    lines = [f"The story is: {headline.rstrip('.')}."]
    blurb = first_sentence(topic.summary)
    if blurb and blurb.casefold() not in headline.casefold() and headline.casefold() not in blurb.casefold():
        lines.append(_ends(blurb))
    lines.extend(_ends(sentence) for sentence in _spoken_parts(_WHY[category]))
    if topic.source:
        lines.append(f"The write-up is from {topic.source}.")
    lines.extend(_spoken_parts("The link is in the caption. Follow for the next AI short."))
    extra = {
        "launch": "AITools",
        "research": "AIResearch",
        "policy": "AIRegulation",
        "news": "AINews",
    }[category]
    return Script(
        title=_youtube_title(headline),
        category=category,
        hook=_pick(_HOOKS[category], headline),
        lines=lines,
        hashtags=["AI", "ArtificialIntelligence", "TechNews", "Shorts", extra],
        topic=topic,
    )


def _extract_json(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _from_llm_payload(payload: dict, topic: Topic) -> Script | None:
    hook = str(payload.get("hook") or "").strip()
    raw_lines = payload.get("lines")
    if not hook or not isinstance(raw_lines, list):
        return None
    lines = [_ends(str(line)) for line in raw_lines if str(line).strip()]
    if not lines:
        return None
    hashtags = payload.get("hashtags")
    tags = [str(tag).lstrip("#").replace(" ", "") for tag in hashtags] if isinstance(hashtags, list) else []
    tags = [tag for tag in tags if tag] or ["AI", "Shorts"]
    title = str(payload.get("title") or topic.title).strip() or topic.title
    script = Script(
        title=_youtube_title(title.replace(" #Shorts", "")),
        category=classify(topic.title),
        hook=hook.strip(),
        lines=lines,
        hashtags=tags[:8],
        topic=topic,
    )
    words = script.spoken.split()
    if not 40 <= len(words) <= 140:
        return None
    # Keep the model from drifting off the headline we actually fetched.
    if topic.title.split()[0].casefold() not in script.spoken.casefold() and topic.title.casefold() not in script.spoken.casefold():
        headline_tokens = [word for word in re.findall(r"[A-Za-z0-9']+", topic.title) if len(word) > 4]
        if headline_tokens and not any(token.casefold() in script.spoken.casefold() for token in headline_tokens[:4]):
            return None
    return script


def llm_script(topic: Topic) -> Script | None:
    api_key = os.environ.get("REELS_LLM_API_KEY", "").strip()
    if not api_key:
        return None
    base = os.environ.get("REELS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("REELS_LLM_MODEL", "gpt-4o-mini")
    prompt = {
        "model": model,
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write 25 to 40 second vertical video scripts about AI news. "
                    "Use only the facts in the user message. Do not invent numbers, quotes, "
                    "benchmarks, or product features. Return JSON with keys title, hook, lines, hashtags."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Title: {topic.title}\nSource: {topic.source}\nBlurb: {topic.summary}\nURL: {topic.url}\n"
                    "hook is one spoken sentence. lines is 3 or 4 short spoken sentences. "
                    "The last line tells the viewer the link is in the caption and to follow. "
                    "Total spoken length 70 to 110 words. hashtags is a list without the # sign."
                ),
            },
        ],
    }
    request = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(prompt).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
    except (OSError, KeyError, IndexError, json.JSONDecodeError, TypeError):
        return None
    payload = _extract_json(content)
    if not payload:
        return None
    return _from_llm_payload(payload, topic)


def clip_script(topic: Topic) -> Script:
    return Script(
        title=_youtube_title(topic.title),
        category="news",
        hook=topic.title.strip(),
        lines=[
            "This cut is from footage you already own.",
            "Add your own B-roll, music, and caption in CapCut before you post.",
        ],
        hashtags=["AI", "Shorts"],
        topic=topic,
    )


def build_script(topic: Topic) -> Script:
    return llm_script(topic) or template_script(topic)
