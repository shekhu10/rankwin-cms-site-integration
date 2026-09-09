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
    def test_tables_require_real_headers_rows_and_cells(self) -> None:
        cell = lambda text: {"children": [{"type": "text", "text": text}]}
        document = {"blocks": [{"type": "table", "header": {"cells": [cell("Tool"), cell("Use")]},
                                "rows": [{"cells": [cell("A & B"), cell("Coding")]}]}]}
        html = "<table><thead><tr><th>Tool</th><th>Use</th></tr></thead><tbody><tr><td>A &amp; B</td><td><strong>Coding</strong></td></tr></tbody></table>"
        verifier.assert_article_tables(document, html)
        for broken in ["<p>Tool | Use | A &amp; B | Coding</p>", "<template>" + html + "</template>",
                       html.replace("<td><strong>Coding</strong></td>", ""), html.replace("th>", "td>")]:
            with self.subTest(source=broken), self.assertRaisesRegex(AssertionError, "table"):
                verifier.assert_article_tables(document, broken)

    def test_article_text_allows_renderer_serialization_but_not_script_only_body(self) -> None:
        body = "<p>Pramp &amp; practice <strong>interviews</strong> today.</p>"
        verifier.assert_article_body(body, "<article><p>Pramp &amp; practice <b>interviews</b> today.</p></article>")
        with self.assertRaisesRegex(AssertionError, "absent"):
            verifier.assert_article_body(body, '<script type="application/json">Pramp & practice interviews today.</script><main>Loading</main>')
        with self.assertRaisesRegex(AssertionError, "absent"):
            verifier.assert_article_body("<p>" + "Beginning " * 30 + "MIDDLE " * 30 + "Ending " * 30 + "</p>", "<p>" + "Beginning " * 30 + "</p>")

    def test_article_layout_requires_title_image_body_order(self) -> None:
        article = {"title": "A & B", "html": "<p>Full article body.</p>",
                   "featuredImage": {"url": "https://cms.example/media/hero", "alt": "Cover"}}
        title = "<h1>A &amp; <span>B</span></h1>"
        image = '<img src="https://cms.example/media/hero" alt="Cover">'
        body = article["html"]
        optimized = '<img src="/_next/image?url=https%3A%2F%2Fcms.example%2Fmedia%2Fhero&amp;w=800" alt="Cover">'
        for source in [title + image + body, title + optimized + body]:
            evidence = verifier.HtmlEvidenceParser()
            evidence.feed(source)
            verifier.assert_article_layout(article, evidence)
        cases = [
            (image + title + body, "title must precede"),
            (title + body + image, "body must follow"),
            (image + body, "one visible h1"),
            (title + title + image + body, "one visible h1"),
            (title + '<script>' + image + '</script>' + body, "image tags"),
            (title + '<template>' + image + '</template>' + body, "image tags"),
            (title + image.replace('Cover', 'Wrong alt') + body, "alt text"),
            (title + image.replace('/hero', '/hero-wrong') + body, "image tags"),
        ]
        for source, error in cases:
            with self.subTest(error=error):
                evidence = verifier.HtmlEvidenceParser()
                evidence.feed(source)
                with self.assertRaisesRegex(AssertionError, error):
                    verifier.assert_article_layout(article, evidence)
        evidence = verifier.HtmlEvidenceParser()
        evidence.feed(title + body)
        verifier.assert_article_layout({**article, "featuredImage": None}, evidence)

    def test_removed_url_requires_404_and_no_collection_links(self) -> None:
        url = "https://www.example.com/blogs/removed"
        site = {"customerBlogUrl": "https://www.example.com/blogs"}
        gone = verifier.HttpResponse(404, {}, b"", url)
        with patch.object(verifier, "request", return_value=gone):
            verifier.verify_removed_urls([url], site, set())
            with self.assertRaisesRegex(AssertionError, "still linked"):
                verifier.verify_removed_urls([url], site, {url})
        with patch.object(verifier, "request", return_value=response("old page", url=url)):
            with self.assertRaisesRegex(AssertionError, "404 or 410"):
                verifier.verify_removed_urls([url], site, set())
        with patch.object(verifier, "request") as fetch:
            with self.assertRaisesRegex(AssertionError, "authenticated customer"):
                verifier.verify_removed_urls(["https://other.example/blogs/a"], site, set())
            fetch.assert_not_called()

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
