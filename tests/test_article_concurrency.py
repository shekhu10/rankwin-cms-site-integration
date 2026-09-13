from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_integration as verifier


class ArticleConcurrencyTests(unittest.TestCase):
    def test_checks_every_article_with_bounded_parallelism(self):
        barrier = threading.Barrier(2, timeout=5)
        lock = threading.Lock()
        seen = []
        active = 0
        maximum = 0

        def check(summary, api_base, api_key):
            nonlocal active, maximum
            self.assertEqual((api_base, api_key), ("base", "key"))
            with lock:
                active += 1
                maximum = max(maximum, active)
                seen.append(summary["id"])
            barrier.wait()
            with lock:
                active -= 1

        articles = [{"id": str(i)} for i in range(6)]
        with patch.object(verifier, "verify_article", side_effect=check):
            verifier.verify_articles(articles, "base", "key", workers=2)
        self.assertEqual(sorted(seen), [str(i) for i in range(6)])
        self.assertEqual(maximum, 2)

    def test_a_failed_article_cannot_produce_a_successful_audit(self):
        def check(summary, *_):
            if summary["id"] == "broken":
                raise AssertionError("featured image is unavailable")

        with patch.object(verifier, "verify_article", side_effect=check):
            with self.assertRaisesRegex(AssertionError, "featured image"):
                verifier.verify_articles([{"id": "ok"}, {"id": "broken"}], "base", "key", 2)

    def test_invalid_parallelism_is_rejected_before_network_access(self):
        with patch.object(verifier, "verify_article") as check:
            for workers in (0, 9):
                with self.assertRaises(ValueError):
                    verifier.verify_articles([{"id": "a"}], "base", "key", workers)
            check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
