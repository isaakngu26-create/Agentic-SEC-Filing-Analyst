# AI short reels

A small pipeline for original commentary shorts:

1. Fetch trending AI headlines from Google News, Hacker News, and Reddit.
2. Write a 30-second script that sticks to that headline.
3. Generate a voiceover and timed captions.
4. Render a 1080x1920 draft you can post or drop into a CapCut template.
5. Save YouTube, TikTok, and Instagram copy. Upload only when you add API tokens, and only as private or draft.

This does not download other people's videos. `clip` only cuts a local file you already have.

## Setup

ffmpeg is required for the draft video. The voiceover uses [edge-tts](https://github.com/rany2/edge-tts).

```bash
pip install -r requirements-reels.txt
```

## Create a short

```bash
python -m reels topics
python -m reels make
python -m reels make --count 3
python -m reels make --topic "OpenAI ships a new coding model" --source "The Verge" --url "https://www.theverge.com/"
```

Each run writes a folder under `output/reels/`:

| File | What it is |
| --- | --- |
| `script.txt` | Spoken lines you can edit |
| `voiceover.mp3` | Neural voiceover |
| `captions.srt` | Captions timed to the voice |
| `draft.mp4` | 1080x1920 rough cut |
| `template.json` | Layer list for a 9:16 CapCut template |
| `EDIT.md` | Click path for CapCut |
| `post/` | Title and captions for each platform |

Play `draft.mp4`. If the script is off, edit `script.txt` and run `make` again with `--topic`.

Set `REELS_LLM_API_KEY` (and optionally `REELS_LLM_BASE_URL` and `REELS_LLM_MODEL`) when you want an OpenAI-compatible model to rewrite the script. Without a key, the built-in template writes the script from the headline and will not invent numbers or quotes.

## CapCut

1. New project, ratio 9:16.
2. Import `draft.mp4`, or import `voiceover.mp3` and your own B-roll.
3. Text, Captions, Import, then choose `captions.srt`.
4. Apply the template you already use. Match the layers in `template.json`: a top kicker (`TODAY IN AI`), the headline, and lower captions.
5. Export 1080x1920 at 30 fps.

Use music and B-roll you have rights to. CapCut's stock library and your own screen recordings are the usual sources. The draft background is plain so the cut is watchable before that edit.

## Clip a local video

```bash
python -m reels clip --video demo.mp4 --start 12 --end 42 --title "My AI demo"
```

`--fit pad` keeps the whole frame. `--fit fill` center-crops to full bleed. Add `--captions take.srt` to burn captions.

## Post

`python -m reels publish output/reels/<folder>` prints the caption files. Nothing is uploaded.

```bash
python -m reels publish output/reels/<folder> --upload
python -m reels publish output/reels/<folder> --upload --platform youtube
```

| Platform | Token | What `--upload` does |
| --- | --- | --- |
| YouTube Shorts | `YOUTUBE_ACCESS_TOKEN` with the `youtube.upload` scope | Private video |
| TikTok | `TIKTOK_ACCESS_TOKEN` from a Content Posting API app | Inbox draft, so you finish it in TikTok |
| Instagram Reels | `IG_ACCESS_TOKEN` and `IG_USER_ID` for a professional account | Reel on that account |

Create those credentials in Google Cloud, the TikTok developer portal, and a Meta app. Leave the tokens out of the repo. Until they are set, paste `post/youtube.txt`, `post/tiktok.txt`, and `post/instagram.txt` into each app by hand.
