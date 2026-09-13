from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_integration as verifier
from index_evidence import IndexEvidenceParser, parse_index_evidence


BLOG = "https://www.example.com/blogs"
SECOND = BLOG + "/page/2"
IMAGE = {"url": "https://cms.example/media/hero", "alt": "The cover"}


def article(slug="a", image=IMAGE):
    return {"slug": slug, "canonicalUrl": f"{BLOG}/{slug}", "featuredImage": image}


def card(slug="a", image=IMAGE):
    media = f'<img src="{image["url"]}" alt="{image["alt"]}">' if image else ""
    return f'<article><a href="{BLOG}/{slug}">Title</a>{media}</article>'


def html(url, body, canonical=None):
    return verifier.HttpResponse(200, {"Content-Type": "text/html"},
                                 f'<link rel="canonical" href="{canonical or url}">{body}'.encode(), url)


def evidence(source):
    result = IndexEvidenceParser()
    result.feed(source)
    return result


class IndexPaginationTests(unittest.TestCase):
    def test_follows_discovered_pagination_and_checks_second_page_card(self):
        bodies = {
            BLOG: html(BLOG, card("a", None) + '<nav aria-label="Blog pagination"><a href="/blogs/page/2">Next</a></nav>'),
            SECOND: html(SECOND, card("b") + '<nav aria-label="Blog pagination"><a href="/blogs">Previous</a><a href="/blogs/page/2">2</a></nav>'),
        }
        with patch.object(verifier, "request", side_effect=lambda url, **kwargs: bodies[url]) as fetch:
            pages = verifier.collect_index_pages(BLOG)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [BLOG, SECOND])
        links = verifier.assert_index_articles([article("a", None), article("b")], pages)
        self.assertTrue({BLOG + "/a", BLOG + "/b"}.issubset(links))

    def test_only_explicit_visible_pagination_is_crawled(self):
        source = '<nav aria-label="Resources"><a href="/pricing">Plans</a></nav><a href="/blogs/page/90">Ordinary link</a><template><a rel="next" href="/blogs/page/3">Hidden</a></template><div hidden><a rel="next" href="/blogs/page/4">Hidden</a></div>'
        with patch.object(verifier, "request", return_value=html(BLOG, source)) as fetch:
            self.assertEqual(len(verifier.collect_index_pages(BLOG)), 1)
        fetch.assert_called_once_with(BLOG, accept="text/html")

    def test_rel_next_and_query_pagination_retain_distinct_canonicals(self):
        second = BLOG + "?page=2"
        bodies = {BLOG: html(BLOG, '<link rel="next" href="?page=2">'), second: html(second, card())}
        with patch.object(verifier, "request", side_effect=lambda url, **kwargs: bodies[url]):
            pages = verifier.collect_index_pages(BLOG)
        self.assertEqual([url for url, _ in pages], [BLOG, second])
        verifier.assert_index_articles([article()], pages)
        with self.assertRaisesRegex(AssertionError, "query"):
            verifier.normalized_public_url(second)

    def test_rejects_pagination_outside_origin_or_blog_before_fetching_it(self):
        for target in ["https://other.example/blogs/page/2", "/admin?page=2", "https://user:pass@www.example.com/blogs/page/2"]:
            with self.subTest(target=target), patch.object(verifier, "request", return_value=html(BLOG, f'<a rel="next" href="{target}">Next</a>')) as fetch:
                with self.assertRaises(AssertionError):
                    verifier.collect_index_pages(BLOG)
                fetch.assert_called_once_with(BLOG, accept="text/html")

    def test_pagination_budget_does_not_fetch_an_unbounded_chain(self):
        def load(url, **kwargs):
            target = SECOND if url == BLOG else BLOG + "/page/3"
            return html(url, f'<a rel="next" href="{target}">Next</a>')
        with patch.object(verifier, "request", side_effect=load) as fetch:
            with self.assertRaisesRegex(AssertionError, "safety limit"):
                verifier.collect_index_pages(BLOG, max_pages=2)
        self.assertEqual(fetch.call_count, 2)

    def test_rejects_stale_pagination_canonical_or_redirect(self):
        first = html(BLOG, '<a rel="next" href="/blogs/page/2">Next</a>')
        for second in [html(SECOND, card(), canonical=BLOG), html(BLOG, card())]:
            with self.subTest(second=second), patch.object(verifier, "request", side_effect=[first, second]):
                with self.assertRaisesRegex(AssertionError, "canonical|redirects"):
                    verifier.collect_index_pages(BLOG)

    def test_all_published_article_links_are_required(self):
        pages = [(BLOG, evidence(card("a", None)))]
        with self.assertRaisesRegex(AssertionError, "missing 1 crawlable"):
            verifier.assert_index_articles([article("a", None), article("b", None)], pages)

    def test_wrapped_and_sibling_link_card_layouts_work(self):
        variants = [card(), '<a href="/blogs/a"><article><img src="https://cms.example/media/hero" alt="The cover"></article></a>', '<div class="blog-card"><img src="https://cms.example/media/hero" alt="The cover"><h2><a href="/blogs/a">Title</a></h2></div>', '<a href="/blogs/a"><img src="https://cms.example/media/hero" alt="The cover">Title</a>']
        for source in variants:
            with self.subTest(source=source):
                verifier.assert_index_articles([article()], [(BLOG, evidence(source))])

    def test_optimizer_url_is_matched_exactly_and_alt_is_required(self):
        source = card().replace(IMAGE["url"], "/_next/image?url=https%3A%2F%2Fcms.example%2Fmedia%2Fhero&amp;w=800")
        verifier.assert_index_articles([article()], [(BLOG, evidence(source))])
        for broken, error in [(source.replace("media%2Fhero", "media%2Fhero-wrong"), "own index card"), (source.replace('alt="The cover"', 'alt="Wrong"'), "alt text"), (source.replace('alt="The cover"', ""), "alt text")]:
            with self.subTest(error=error), self.assertRaisesRegex(AssertionError, error):
                verifier.assert_index_articles([article()], [(BLOG, evidence(broken))])

    def test_another_cards_image_cannot_satisfy_this_article(self):
        source = card("a", None) + card("b")
        with self.assertRaisesRegex(AssertionError, "own index card"):
            verifier.assert_index_articles([article("a"), article("b")], [(BLOG, evidence(source))])

    def test_unrelated_global_or_script_image_does_not_satisfy_a_card(self):
        media = '<img src="https://cms.example/media/hero" alt="The cover">'
        for source in [media + card("a", None), card("a", None) + '<script type="application/json">' + media + '</script>', card("a", None).replace('</article>', '<template>' + media + '</template></article>')]:
            with self.subTest(source=source), self.assertRaisesRegex(AssertionError, "own index card"):
                verifier.assert_index_articles([article()], [(BLOG, evidence(source))])

    def test_hidden_article_links_do_not_count(self):
        with self.assertRaisesRegex(AssertionError, "missing 1 crawlable"):
            verifier.assert_index_articles([article()], [(BLOG, evidence('<div aria-hidden="true">' + card() + '</div>'))])

    def test_removed_link_on_later_page_is_in_union(self):
        pages = [(BLOG, evidence(card("a", None))), (SECOND, evidence('<a href="/blogs/removed">Old article</a>'))]
        links = verifier.assert_index_articles([article("a", None)], pages)
        with patch.object(verifier, "request") as fetch, self.assertRaisesRegex(AssertionError, "still linked"):
            verifier.verify_removed_urls([BLOG + "/removed"], {"customerBlogUrl": BLOG}, links)
        fetch.assert_not_called()

    def test_completed_react_streaming_resolves_nested_transport_content(self):
        source = '<template id="B:0"></template><div hidden id="S:0"><template id="P:1"></template></div><div hidden id="S:1">' + card() + '<nav aria-label="Pagination"><a href="/blogs/page/2">Next</a></nav></div><script>$RS("S:1","P:1")</script><script>function example(){};$RC("B:0","S:0")</script>'
        parsed = parse_index_evidence(source)
        verifier.assert_index_articles([article()], [(BLOG, parsed)])
        self.assertEqual(parsed.pagination_links, ["/blogs/page/2"])
        with self.assertRaisesRegex(AssertionError, "missing 1 crawlable"):
            verifier.assert_index_articles([article()], [(BLOG, parse_index_evidence(source.replace('$RC("B:0","S:0")', '')))])

    def test_fake_streaming_markers_do_not_unhide_cards(self):
        prefix = '<template id="B:0"></template><div hidden id="S:0">' + card() + '</div>'
        for suffix in ['', '<script type="application/json">"$RC(\\"B:0\\",\\"S:0\\")"</script>', '<script>console.log(\'$RC("B:0","S:0")\')</script>', '<script>$RC("B:9","S:0")</script>']:
            with self.subTest(suffix=suffix), self.assertRaisesRegex(AssertionError, "missing 1 crawlable"):
                verifier.assert_index_articles([article()], [(BLOG, parse_index_evidence(prefix + suffix))])

    def test_completed_stream_does_not_override_hidden_card_or_target(self):
        for content in ['<div hidden>' + card() + '</div>', '<div aria-hidden="true">' + card() + '</div>']:
            source = '<template id="B:0"></template><div hidden id="S:0">' + content + '</div><script>$RC("B:0","S:0")</script>'
            with self.assertRaisesRegex(AssertionError, "missing 1 crawlable"):
                verifier.assert_index_articles([article()], [(BLOG, parse_index_evidence(source))])
        source = '<div hidden><template id="B:0"></template></div><div hidden id="S:0">' + card() + '</div><script>$RC("B:0","S:0")</script>'
        with self.assertRaisesRegex(AssertionError, "missing 1 crawlable"):
            verifier.assert_index_articles([article()], [(BLOG, parse_index_evidence(source))])


if __name__ == "__main__":
    unittest.main()
