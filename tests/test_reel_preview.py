from html.parser import HTMLParser

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class PreviewElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.videos = []
        self.overlays = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "video":
            self.videos.append(attrs)
        if tag == "div" and "absolute" in attrs.get("class", "").split():
            self.overlays.append(attrs)


class ReelPlaybackTests(SimpleTestCase):
    def test_reel_has_audio_and_playback_controls_without_blocking_overlays(self):
        for platform in ("instagram", "instagram_personal"):
            with self.subTest(platform=platform):
                html = render_to_string("composer/partials/preview_panel.html", {
                    "previews": [{
                        "account": {"platform": platform, "account_name": "Jobz"},
                        "ig_format": "reel", "caption": "Meu Reel",
                        "truncated_caption": "Meu Reel", "char_count": 8,
                        "char_limit": 2200,
                    }],
                    "media_items": [{"url": "/media/reel.mp4", "is_video": True}],
                })
                elements = PreviewElements()
                elements.feed(html)
                self.assertEqual(len(elements.videos), 1)
                video = elements.videos[0]
                self.assertIn("controls", video)
                self.assertIn("playsinline", video)
                self.assertNotIn("muted", video)
                self.assertEqual(video["src"], "/media/reel.mp4")
                for overlay in elements.overlays:
                    self.assertIn("pointer-events-none", overlay["class"])
