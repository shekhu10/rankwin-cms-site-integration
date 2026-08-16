from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_integration as verifier  # noqa: E402


def response(
    body: str,
    *,
    content_type: str = "application/xml",
    url: str = "https://www.example.com/sitemap.xml",
) -> verifier.HttpResponse:
    return verifier.HttpResponse(
        status=200,
        headers={"Content-Type": content_type},
        body=body.encode(),
        final_url=url,
    )


class VerifyIntegrationTests(unittest.TestCase):
    def test_rejects_canonical_host_redirect(self) -> None:
        redirected = verifier.HttpResponse(
            200,
            {"Content-Type": "text/html"},
            b"",
            "https://www.example.com/blogs",
        )
        with self.assertRaisesRegex(AssertionError, "redirects away"):
            verifier.assert_no_redirect(
                redirected, "https://example.com/blogs", "customer index"
            )

    def test_requires_ids_on_nested_document_nodes(self) -> None:
        document = {
            "id": "document-1",
            "blocks": [
                {
                    "id": "block-1",
                    "type": "paragraph",
                    "children": [{"type": "text", "text": "missing id"}],
                }
            ],
        }
        with self.assertRaisesRegex(AssertionError, "stable node id"):
            verifier.collect_document_node_ids(document)

    def test_rejects_duplicate_nested_document_ids(self) -> None:
        document = {
            "id": "document-1",
            "blocks": [
                {
                    "id": "duplicate",
                    "type": "paragraph",
                    "children": [
                        {"id": "duplicate", "type": "text", "text": "text"}
                    ],
                }
            ],
        }
        ids = verifier.collect_document_node_ids(document)
        self.assertNotEqual(len(ids), len(set(ids)))

    def test_sitemap_url_inside_urlset_is_not_registration(self) -> None:
        robots = response("User-agent: *\n", content_type="text/plain")
        root = response(
            """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://www.example.com/blogs/sitemap.xml</loc></url>
            </urlset>"""
        )
        with patch.object(verifier, "request", side_effect=[robots, root]):
            with self.assertRaisesRegex(AssertionError, "not registered"):
                verifier.verify_sitemap_registration(
                    "https://www.example.com",
                    "https://www.example.com/blogs/sitemap.xml",
                    {"https://www.example.com/blogs/article"},
                )

    def test_registered_child_sitemap_is_accepted(self) -> None:
        robots = response(
            "Sitemap: https://www.example.com/blogs/sitemap.xml\n",
            content_type="text/plain",
        )
        with patch.object(verifier, "request", return_value=robots):
            verifier.verify_sitemap_registration(
                "https://www.example.com",
                "https://www.example.com/blogs/sitemap.xml",
                {"https://www.example.com/blogs/article"},
            )

    def test_registered_root_index_may_merge_articles_in_child(self) -> None:
        robots = response("User-agent: *\n", content_type="text/plain")
        root = response(
            """<?xml version="1.0"?>
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://www.example.com/sitemap-0.xml</loc></sitemap>
            </sitemapindex>"""
        )
        child = response(
            """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://www.example.com/blogs/article</loc></url>
            </urlset>""",
            url="https://www.example.com/sitemap-0.xml",
        )
        with patch.object(verifier, "request", side_effect=[robots, root, child]):
            verifier.verify_sitemap_registration(
                "https://www.example.com",
                "https://www.example.com/blogs/sitemap.xml",
                {"https://www.example.com/blogs/article"},
            )

    def test_sitemap_scope_rejects_another_customer(self) -> None:
        site = {
            "host": "www.example.com",
            "blogPath": "/blogs",
            "customerBlogUrl": "https://www.example.com/blogs/",
        }
        with self.assertRaisesRegex(AssertionError, "leaks"):
            verifier.assert_site_scoped_urls(
                {"https://other.example/blogs/article"},
                {"https://www.example.com/blogs/article"},
                site,
                "sitemap",
            )

    def test_atom_alternate_links_are_collected(self) -> None:
        root = ET.fromstring(
            """<feed xmlns="http://www.w3.org/2005/Atom">
              <entry><link rel="alternate" href="https://www.example.com/blogs/a" /></entry>
              <entry><link rel="self" href="https://api.example/feed" /></entry>
            </feed>"""
        )
        self.assertEqual(
            verifier.feed_locations(root), {"https://www.example.com/blogs/a"}
        )


if __name__ == "__main__":
    unittest.main()
