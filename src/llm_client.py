"""OpenAI client helper."""

import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_openai_client() -> "OpenAI":
    if OpenAI is None:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your environment or Streamlit secrets."
        )
    return OpenAI(api_key=api_key)


def get_model() -> str:
    return DEFAULT_MODEL
