import unittest

from reels.captions import Cue, ass_escape, build_ass, even_captions, parse_srt, readable_captions
from reels.publish import instagram_caption, tiktok_source_info, youtube_metadata
from reels.render import fit_filter
from reels.script import classify, template_script
from reels.topics import Topic, dedupe, is_ai_topic, mix_sources, parse_google_news_xml, parse_hn_hits


GOOGLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>OpenAI ships a new coding model - The Verge</title>
  <link>https://news.google.com/rss/articles/example</link>
  <pubDate>Wed, 14 Oct 2026 12:00:00 GMT</pubDate>
  <description>The company released a model aimed at software work.</description>
  <source url="https://www.theverge.com">The Verge</source>
</item>
</channel></rss>
"""


class TopicTests(unittest.TestCase):
    def test_google_news_strips_publisher_suffix(self):
        topics = parse_google_news_xml(GOOGLE)
        self.assertEqual(topics[0].title, "OpenAI ships a new coding model")
        self.assertEqual(topics[0].source, "The Verge")
        self.assertIn("software work", topics[0].summary)

    def test_ai_filter_and_dedupe(self):
        self.assertTrue(is_ai_topic("OpenAI ships a coding model"))
        self.assertFalse(is_ai_topic("A new email app launches"))
        hits = parse_hn_hits(
            [
                {"title": "OpenAI ships a coding model", "url": "https://openai.com/x", "points": 100},
                {"title": "OpenAI ships a coding model", "url": "https://news.ycombinator.com/item?id=1", "points": 10},
                {"title": "Farm prices rise", "url": "https://example.com", "points": 80},
            ]
        )
        unique = dedupe(hits)
        self.assertEqual(len(unique), 2)
        ai_only = [topic for topic in unique if is_ai_topic(topic.title)]
        mixed = mix_sources(ai_only, limit=3)
        self.assertEqual(mixed[0].title, "OpenAI ships a coding model")

    def test_mix_rotates_sources(self):
        topics = [
            Topic("News A", "", "a", "google-news", 1),
            Topic("News B", "", "b", "google-news", 1),
            Topic("HN A", "", "c", "hacker-news", 9),
        ]
        mixed = mix_sources(topics, limit=3)
        self.assertEqual([item.origin for item in mixed], ["google-news", "hacker-news", "google-news"])


class ScriptTests(unittest.TestCase):
    def test_template_uses_the_headline_and_stays_short(self):
        topic = Topic(
            title="OpenAI ships a new coding model",
            url="https://www.theverge.com/story",
            source="The Verge",
            origin="google-news",
            score=10,
            summary="The company released a model aimed at software work.",
        )
        script = template_script(topic)
        self.assertEqual(classify(topic.title), "launch")
        self.assertIn("coding model", script.spoken)
        self.assertIn("The Verge", script.spoken)
        self.assertIn("caption", script.spoken)
        self.assertGreaterEqual(len(script.spoken.split()), 45)
        self.assertLessEqual(len(script.spoken.split()), 130)
        self.assertTrue(script.title.endswith("#Shorts"))

    def test_youtube_upload_stays_private(self):
        topic = Topic("Anthropic research finds a limit", "https://example.com", "Example", "google-news", 1)
        meta = youtube_metadata(template_script(topic))
        self.assertEqual(meta["status"]["privacyStatus"], "private")
        self.assertIn("https://example.com", meta["snippet"]["description"])
        self.assertIn("#AI", instagram_caption(template_script(topic)))

    def test_tiktok_chunks(self):
        small = tiktok_source_info(1000)
        self.assertEqual(small["total_chunk_count"], 1)
        self.assertEqual(small["chunk_size"], 1000)
        large = tiktok_source_info(12 * 1024 * 1024)
        self.assertGreater(large["total_chunk_count"], 1)


class CaptionTests(unittest.TestCase):
    def test_word_cues_become_phrases(self):
        words = []
        for index, word in enumerate("OpenAI ships a new coding model today".split()):
            words.append(Cue(index * 0.4, index * 0.4 + 0.4, word))
        grouped = readable_captions(words, max_words=4)
        self.assertEqual(grouped[0].text, "OpenAI ships a new")
        self.assertEqual(grouped[1].text, "coding model today")
        parsed = parse_srt(
            "1\n00:00:00,000 --> 00:00:01,000\nOpenAI ships a new coding model today and beyond\n"
        )
        split = readable_captions(parsed, max_words=4)
        self.assertGreater(len(split), 1)

    def test_even_captions_and_ass_escape(self):
        cues = even_captions(["Hello there.", "Second line."], 4)
        self.assertEqual(cues[1].start, 2)
        self.assertIn(r"\{boom\}", ass_escape("{boom}"))
        ass = build_ass(cues, "A headline about {AI}")
        self.assertIn("TODAY IN AI", ass)
        self.assertIn(r"\{AI\}", ass)


class RenderTests(unittest.TestCase):
    def test_fit_filters(self):
        self.assertIn("crop=1080:1920", fit_filter("fill"))
        self.assertIn("pad=1080:1920", fit_filter("pad"))
        with self.assertRaises(ValueError):
            fit_filter("stretch")


if __name__ == "__main__":
    unittest.main()
