import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_integration as verifier

BLOG = "https://www.example.com/blogs"
URL = BLOG + "/future-article"
SITE = {"customerBlogUrl": BLOG}


class ScheduledVisibilityTests(unittest.TestCase):
    def test_future_article_is_unlisted_and_returns_404(self):
        with patch.object(verifier, "request", return_value=verifier.HttpResponse(404, {}, b"", URL)):
            verifier.verify_removed_urls([URL], SITE, set(), scheduled=True)

    def test_future_article_must_not_appear_on_any_archive_page(self):
        with patch.object(verifier, "request") as fetch, self.assertRaisesRegex(AssertionError, "scheduled URL is still linked"):
            verifier.verify_removed_urls([URL], SITE, {URL}, scheduled=True)
        fetch.assert_not_called()

    def test_early_publication_and_deleted_status_are_rejected(self):
        for status in [200, 301, 410, 500]:
            with self.subTest(status=status), patch.object(verifier, "request", return_value=verifier.HttpResponse(status, {}, b"", URL)), self.assertRaises(AssertionError):
                verifier.verify_removed_urls([URL], SITE, set(), scheduled=True)

    def test_outside_site_or_blog_is_rejected_before_request(self):
        for url in ["https://other.example/blogs/future", "https://www.example.com/account", BLOG + "/"]:
            with self.subTest(url=url), patch.object(verifier, "request") as fetch, self.assertRaises(AssertionError):
                verifier.verify_removed_urls([url], SITE, set(), scheduled=True)
            fetch.assert_not_called()

    def test_redirect_to_home_does_not_count_as_private(self):
        with patch.object(verifier, "request", return_value=verifier.HttpResponse(404, {}, b"", BLOG)), self.assertRaises(AssertionError):
            verifier.verify_removed_urls([URL], SITE, set(), scheduled=True)

    def test_removed_article_retains_410_support(self):
        with patch.object(verifier, "request", return_value=verifier.HttpResponse(410, {}, b"", URL)):
            verifier.verify_removed_urls([URL], SITE, set())


if __name__ == "__main__":
    unittest.main()
