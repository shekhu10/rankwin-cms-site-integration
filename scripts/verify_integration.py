#!/usr/bin/env python3
"""Verify RankWin CMS API isolation and same-origin customer delivery."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser

from discover_site import configured_value, parse_site, validate_api_base
from table_evidence import assert_article_tables


MAX_PAGES = 100
NODE_ARRAY_KEYS = {
    "answer",
    "attribution",
    "blocks",
    "caption",
    "cells",
    "children",
    "description",
    "header",
    "items",
    "question",
    "rows",
    "title",
}


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    final_url: str


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "template"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(source: str) -> str:
    parser = VisibleTextParser()
    parser.feed(source)
    return " ".join(" ".join(parser.parts).split())


def assert_article_body(expected_html: str, customer_html: str) -> None:
    expected = visible_text(expected_html)
    actual = visible_text(customer_html)
    if not expected:
        raise AssertionError("article body is empty")
    # Customer renderers may insert widgets between blocks. Check text from
    # the beginning, middle and end, independent of HTML/entity serialization.
    starts = {0, max(0, len(expected) // 2 - 80), max(0, len(expected) - 160)}
    if any(expected[start:start + 160] not in actual for start in starts):
        raise AssertionError("article body is absent from initial HTML")


class HtmlEvidenceParser(VisibleTextParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.links: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.image_text_offsets: list[int] = []
        self.headings: list[tuple[int, str]] = []
        self._heading_start: int | None = None
        self.json_ld_count = 0
        self.meta: dict[str, str] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        super().handle_starttag(tag, attrs)
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "h1" and not self.hidden:
            self._heading_start = len(self.parts)
        if tag.lower() == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonicals.append(values.get("href", ""))
        if tag.lower() == "meta" and values.get("name"):
            self.meta[values["name"]] = values.get("content", "")
        if tag.lower() == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag.lower() == "img" and values.get("src") and not self.hidden:
            self.images.append((values["src"], values.get("alt", "")))
            self.image_text_offsets.append(len(self.parts))
        if (
            tag.lower() == "script"
            and values.get("type", "").lower() == "application/ld+json"
        ):
            self.json_ld_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._heading_start is not None:
            title = " ".join(" ".join(self.parts[self._heading_start:]).split())
            self.headings.append((len(self.parts), title))
            self._heading_start = None
        super().handle_endtag(tag)


def assert_article_layout(article: dict, evidence: HtmlEvidenceParser) -> None:
    title = " ".join(article["title"].split())
    if len(evidence.headings) != 1 or evidence.headings[0][1] != title:
        raise AssertionError("article must have one visible h1 containing its title")
    image = article.get("featuredImage")
    if not image:
        return
    matches = [
        (offset, alt)
        for (source, alt), offset in zip(evidence.images, evidence.image_text_offsets)
        if source == image["url"] or image["url"] in urllib.parse.parse_qs(
            urllib.parse.urlsplit(source).query
        ).get("url", [])
    ]
    if not matches:
        raise AssertionError("featured image is absent from initial article image tags")
    image_offset, alt = matches[0]
    if image_offset < evidence.headings[0][0]:
        raise AssertionError("article title must precede the featured image")
    if alt != image["alt"]:
        raise AssertionError("featured image alt text does not match RankWin")
    body_start = visible_text(article["html"])[:160]
    after_image = " ".join(" ".join(evidence.parts[image_offset:]).split())
    if body_start not in after_image:
        raise AssertionError("article body must follow the featured image")


def request(
    url: str,
    *,
    api_key: str | None = None,
    etag: str | None = None,
    accept: str | None = None,
) -> HttpResponse:
    headers = {"User-Agent": "rankwin-cms-integration-verifier/2.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if etag:
        headers["If-None-Match"] = etag
    if accept:
        headers["Accept"] = accept
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=20
        ) as response:
            return HttpResponse(
                response.status,
                dict(response.headers.items()),
                response.read(),
                response.geturl(),
            )
    except urllib.error.HTTPError as error:
        return HttpResponse(
            error.code,
            dict(error.headers.items()),
            error.read(),
            error.geturl(),
        )
    except Exception as error:  # Never include the capability-bearing URL.
        raise RuntimeError(f"request failed: {type(error).__name__}") from error


def response_header(response: HttpResponse, name: str) -> str | None:
    expected = name.casefold()
    return next(
        (value for key, value in response.headers.items() if key.casefold() == expected),
        None,
    )


def json_response(url: str, api_key: str) -> tuple[dict, HttpResponse]:
    response = request(url, api_key=api_key, accept="application/json")
    if response.status != 200:
        raise AssertionError(f"expected 200 JSON, received {response.status}")
    if "application/json" not in (response_header(response, "Content-Type") or ""):
        raise AssertionError("response is not application/json")
    try:
        payload = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise AssertionError("response body is not valid JSON") from error
    if not isinstance(payload, dict):
        raise AssertionError("JSON response is not an object")
    return payload, response


def normalized_public_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "::1",
        "localhost",
    }
    if (parsed.scheme != "https" and not local_http) or not parsed.netloc:
        raise AssertionError("public URL must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AssertionError("public URL contains credentials, query, or fragment data")
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", "")
    )


def assert_no_redirect(response: HttpResponse, expected_url: str, label: str) -> None:
    if normalized_public_url(response.final_url) != normalized_public_url(expected_url):
        raise AssertionError(
            f"{label} redirects away from the RankWin canonical: "
            f"expected {normalized_public_url(expected_url)}, "
            f"received {normalized_public_url(response.final_url)}"
        )


def assert_html(
    response: HttpResponse, expected_url: str, label: str
) -> tuple[str, HtmlEvidenceParser]:
    if response.status != 200:
        raise AssertionError(f"customer {label} returned {response.status}")
    if "text/html" not in (response_header(response, "Content-Type") or ""):
        raise AssertionError(f"customer {label} is not HTML")
    assert_no_redirect(response, expected_url, f"customer {label}")
    source = response.body.decode("utf-8", errors="replace")
    parser = HtmlEvidenceParser()
    parser.feed(source)
    canonical_urls = {
        normalized_public_url(value) for value in parser.canonicals if value
    }
    if normalized_public_url(expected_url) not in canonical_urls:
        raise AssertionError(
            f"customer {label} canonical does not exactly match its final URL"
        )
    return source, parser


def assert_summary(summary: object, site: dict[str, str]) -> dict:
    if not isinstance(summary, dict):
        raise AssertionError("article summary is not an object")
    for field in (
        "id",
        "publicationId",
        "slug",
        "title",
        "metaDescription",
        "canonicalUrl",
        "publishedAt",
        "updatedAt",
    ):
        if not isinstance(summary.get(field), str) or not summary[field]:
            raise AssertionError(f"list summary missing {field}")
    slug = summary["slug"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise AssertionError("article summary has an invalid slug")
    blog = site["customerBlogUrl"].rstrip("/")
    expected_canonical = f"{blog}/{slug}"
    if normalized_public_url(summary["canonicalUrl"]) != normalized_public_url(
        expected_canonical
    ):
        raise AssertionError("article canonical is outside the authenticated site/path")
    featured_image = summary.get("featuredImage")
    if featured_image is not None and not (
        isinstance(featured_image, dict)
        and isinstance(featured_image.get("id"), str)
        and bool(featured_image["id"])
        and isinstance(featured_image.get("alt"), str)
        and bool(featured_image["alt"].strip())
        and isinstance(featured_image.get("url"), str)
        and featured_image["url"].startswith("https://")
    ):
        raise AssertionError("list summary has an invalid featuredImage")
    return summary


def collect_articles(
    api_base: str, api_key: str, *, allow_empty: bool = False
) -> tuple[dict[str, str], list[dict]]:
    articles: list[dict] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    site: dict[str, str] | None = None
    for _ in range(MAX_PAGES):
        query = {"limit": "50"}
        if cursor:
            query["cursor"] = cursor
        payload, _ = json_response(
            f"{api_base}/articles?{urllib.parse.urlencode(query)}", api_key
        )
        if payload.get("apiVersion") != "cms.v1":
            raise AssertionError("unexpected API version")
        page_site = parse_site(payload)
        if site is None:
            site = page_site
        elif page_site != site:
            raise AssertionError("site discovery changed between list pages")
        page_articles = payload.get("articles")
        if not isinstance(page_articles, list):
            raise AssertionError("articles is not a list")
        articles.extend(assert_summary(item, site) for item in page_articles)
        next_cursor = payload.get("nextCursor")
        if next_cursor is None:
            break
        if not isinstance(next_cursor, str) or not next_cursor:
            raise AssertionError("nextCursor is invalid")
        if next_cursor in seen_cursors:
            raise AssertionError("RankWin returned a repeated pagination cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    else:
        raise AssertionError("article pagination exceeded its safety limit")
    if site is None:
        raise AssertionError("site discovery was not returned")
    if not articles and not allow_empty:
        raise AssertionError("no published articles")
    ids = [article["id"] for article in articles]
    if len(ids) != len(set(ids)):
        raise AssertionError("article IDs are not unique")
    slugs = [article["slug"] for article in articles]
    if len(slugs) != len(set(slugs)):
        raise AssertionError("article slugs are not unique within the site")
    return site, articles


def collect_document_node_ids(
    value: object,
    *,
    path: str = "document",
    node_expected: bool = False,
) -> list[str]:
    ids: list[str] = []
    if isinstance(value, dict):
        node_id = value.get("id")
        if node_expected or "type" in value:
            if not isinstance(node_id, str) or not node_id:
                raise AssertionError(f"{path} is missing a stable node id")
        if isinstance(node_id, str) and node_id:
            ids.append(node_id)
        for key, child in value.items():
            ids.extend(
                collect_document_node_ids(
                    child,
                    path=f"{path}.{key}",
                    node_expected=key in NODE_ARRAY_KEYS,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            ids.extend(
                collect_document_node_ids(
                    child,
                    path=f"{path}[{index}]",
                    node_expected=node_expected,
                )
            )
    return ids


def parse_xml(response: HttpResponse, label: str) -> ET.Element:
    if response.status != 200:
        raise AssertionError(f"customer {label} returned {response.status}")
    content_type = response_header(response, "Content-Type") or ""
    if "xml" not in content_type and "atom" not in content_type:
        raise AssertionError(f"customer {label} is not XML")
    try:
        return ET.fromstring(response.body)
    except ET.ParseError as error:
        raise AssertionError(f"customer {label} is invalid XML") from error


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sitemap_locations(root: ET.Element) -> tuple[str, set[str]]:
    kind = local_name(root.tag)
    if kind not in {"urlset", "sitemapindex"}:
        raise AssertionError("sitemap root must be urlset or sitemapindex")
    parent = "url" if kind == "urlset" else "sitemap"
    locations: set[str] = set()
    for child in root:
        if local_name(child.tag) != parent:
            continue
        location = next(
            (
                node.text.strip()
                for node in child
                if local_name(node.tag) == "loc" and node.text
            ),
            None,
        )
        if location:
            locations.add(normalized_public_url(location))
    return kind, locations


def feed_locations(root: ET.Element) -> set[str]:
    if local_name(root.tag) != "feed":
        raise AssertionError("feed root must be Atom feed")
    locations: set[str] = set()
    for element in root.iter():
        if local_name(element.tag) != "link":
            continue
        href = element.attrib.get("href")
        relation = element.attrib.get("rel", "alternate")
        if href and relation == "alternate":
            locations.add(normalized_public_url(href))
    return locations


def assert_site_scoped_urls(
    locations: set[str], expected: set[str], site: dict[str, str], label: str
) -> None:
    blog = normalized_public_url(site["customerBlogUrl"])
    allowed_prefix = blog if blog.endswith("/") else f"{blog}/"
    for location in locations:
        if location != blog and not location.startswith(allowed_prefix):
            raise AssertionError(f"{label} leaks a URL outside the authenticated site/path")
    missing = expected - locations
    if missing:
        raise AssertionError(f"{label} is missing {len(missing)} published article URL(s)")


def verify_sitemap_registration(
    customer_origin: str, customer_sitemap_url: str, expected_articles: set[str]
) -> None:
    normalized_customer_sitemap = normalized_public_url(customer_sitemap_url)
    robots = request(f"{customer_origin}/robots.txt", accept="text/plain")
    if robots.status == 200:
        sitemap_lines = {
            normalized_public_url(match.group(1).strip())
            for match in re.finditer(
                r"(?im)^\s*Sitemap:\s*(\S+)\s*$",
                robots.body.decode("utf-8", errors="replace"),
            )
        }
        if normalized_customer_sitemap in sitemap_lines:
            return

    root_response = request(f"{customer_origin}/sitemap.xml", accept="application/xml")
    root = parse_xml(root_response, "root sitemap")
    kind, locations = sitemap_locations(root)
    if kind == "sitemapindex" and normalized_customer_sitemap in locations:
        return
    if kind == "sitemapindex":
        for child_sitemap in sorted(locations)[:100]:
            child_response = request(child_sitemap, accept="application/xml")
            child_root = parse_xml(child_response, "registered child sitemap")
            child_kind, child_locations = sitemap_locations(child_root)
            if child_kind == "urlset" and expected_articles.issubset(child_locations):
                return
    if kind == "urlset" and expected_articles.issubset(locations):
        return
    raise AssertionError(
        "RankWin sitemap is not registered in robots.txt, a sitemap index, "
        "or a root sitemap that contains every published canonical"
    )


def optional_isolation_checks(api_base: str, api_key: str, article_id: str) -> list[str]:
    skipped: list[str] = []
    other_base_raw = os.environ.get("RANKWIN_CMS_OTHER_API_BASE", "").strip()
    other_key = os.environ.get("RANKWIN_CMS_OTHER_API_KEY", "").strip()
    if other_base_raw and other_key:
        other_base = validate_api_base(other_base_raw)
        encoded_id = urllib.parse.quote(article_id, safe="")
        if request(
            f"{api_base}/articles/by-id/{encoded_id}", api_key=other_key
        ).status != 401:
            raise AssertionError("another site's key was accepted by this site")
        if request(
            f"{other_base}/articles/by-id/{encoded_id}", api_key=api_key
        ).status != 401:
            raise AssertionError("this site's key was accepted by another site")
    else:
        skipped.append(
            "cross-site valid-key isolation (set RANKWIN_CMS_OTHER_API_BASE and "
            "RANKWIN_CMS_OTHER_API_KEY to exercise it live)"
        )

    revoked_key = os.environ.get("RANKWIN_CMS_REVOKED_API_KEY", "").strip()
    if revoked_key:
        if request(f"{api_base}/articles?limit=1", api_key=revoked_key).status != 401:
            raise AssertionError("the revoked delivery key is still accepted")
    else:
        skipped.append(
            "revoked-key rejection (set RANKWIN_CMS_REVOKED_API_KEY after rotation)"
        )
    return skipped


def verify_removed_urls(urls: list[str], site: dict, visible_urls: set[str]) -> None:
    """Read-only verification of URLs the operator has already unpublished."""
    origin = urllib.parse.urlsplit(site["customerBlogUrl"])
    prefix = origin.path.rstrip("/") + "/"
    for raw in urls:
        url = normalized_public_url(raw)
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc) or not parsed.path.startswith(prefix) or parsed.path == prefix:
            raise AssertionError("removed URL must be an article under the authenticated customer blog")
        if url in visible_urls:
            raise AssertionError("removed URL is still linked in the sitemap, feed, or index")
        result = request(raw, accept="text/html")
        assert_no_redirect(result, raw, "removed article")
        if result.status not in (404, 410):
            raise AssertionError("removed article must return HTTP 404 or 410")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", help="defaults to RANKWIN_CMS_API_BASE")
    parser.add_argument("--customer-blog-url")
    parser.add_argument("--removed-url", action="append", default=[], help="already unpublished customer URL; repeat for multiple URLs")
    args = parser.parse_args()
    api_base = validate_api_base(
        configured_value(args.api_base, "RANKWIN_CMS_API_BASE")
    )
    api_key = configured_value(None, "RANKWIN_CMS_API_KEY")

    if request(f"{api_base}/articles?limit=1").status != 401:
        raise AssertionError("unauthenticated list did not return 401")
    if request(
        f"{api_base}/articles?limit=1", api_key=f"rwcms_live_{'A' * 43}"
    ).status != 401:
        raise AssertionError("malformed/invalid key did not return 401")

    site, articles = collect_articles(api_base, api_key, allow_empty=bool(args.removed_url))
    expected_blog_url = normalized_public_url(site["customerBlogUrl"])
    customer_blog_url = normalized_public_url(
        args.customer_blog_url or site["customerBlogUrl"]
    )
    if customer_blog_url != expected_blog_url:
        raise AssertionError(
            "customer blog URL does not match authenticated site.blogPath: "
            f"expected {site['customerBlogUrl']}"
        )

    marker_url = f"https://{site['host']}/.well-known/rankwin-site"
    marker_response = request(marker_url, accept="text/plain")
    assert_no_redirect(marker_response, marker_url, "customer RankWin site marker")
    if not (response_header(marker_response, "Content-Type") or "").startswith(
        "text/plain"
    ):
        raise AssertionError("customer RankWin site marker is not text/plain")
    if "no-store" not in (
        response_header(marker_response, "Cache-Control") or ""
    ):
        raise AssertionError("customer RankWin site marker is not no-store")
    if marker_response.body.decode("utf-8", errors="strict").strip() != (
        f"rankwin-site:{site['id']}"
    ):
        raise AssertionError(
            "customer RankWin site marker does not match authenticated site.id"
        )

    blog_response = request(customer_blog_url, accept="text/html")
    index_source, index_html = assert_html(
        blog_response, customer_blog_url, "index"
    )
    expected_canonicals = {
        normalized_public_url(article["canonicalUrl"]) for article in articles
    }

    for summary in articles:
        article_id = urllib.parse.quote(summary["id"], safe="")
        detail, detail_response = json_response(
            f"{api_base}/articles/by-id/{article_id}", api_key
        )
        article = detail.get("article")
        if not isinstance(article, dict):
            raise AssertionError("detail response is missing article")
        for field in ("documentId", "html", "markdown", "seo", "jsonLd"):
            if not article.get(field):
                raise AssertionError(f"detail missing {field}")
        if article.get("id") != summary["id"]:
            raise AssertionError("ID detail mismatch")
        if article.get("featuredImage") != summary.get("featuredImage"):
            raise AssertionError("list/detail featuredImage mismatch")
        document = article.get("document")
        if not isinstance(document, dict) or not document.get("blocks"):
            raise AssertionError("document has no blocks")
        node_ids = collect_document_node_ids(document)
        if not node_ids or len(node_ids) != len(set(node_ids)):
            raise AssertionError("document node IDs are missing or not unique")

        etag = response_header(detail_response, "ETag")
        if not etag:
            raise AssertionError("detail has no ETag")
        if request(
            f"{api_base}/articles/by-id/{article_id}",
            api_key=api_key,
            etag=etag,
        ).status != 304:
            raise AssertionError("conditional detail did not return 304")

        article_url = normalized_public_url(summary["canonicalUrl"])
        article_response = request(article_url, accept="text/html")
        article_source, article_html = assert_html(
            article_response, article_url, f"article {summary['slug']}"
        )
        if visible_text(article["title"]) not in visible_text(article_source):
            raise AssertionError("article title is absent from initial HTML")
        if article_html.json_ld_count == 0:
            raise AssertionError("article JSON-LD is absent from initial HTML")
        assert_article_body(article["html"], article_source)
        assert_article_layout(article, article_html)
        assert_article_tables(article["document"], article["html"])
        assert_article_tables(article["document"], article_source)
        if article.get("snapshotDigest"):
            markers = {"rankwin-publication-id": article["publicationId"],
                       "rankwin-content-version": str(article["contentVersion"]),
                       "rankwin-snapshot-digest": article["snapshotDigest"]}
            for name, expected in markers.items():
                if article_html.meta.get(name) != expected:
                    raise AssertionError(f"publication marker {name} is missing or stale")

        featured_image = summary.get("featuredImage")
        if featured_image:
            media = request(featured_image["url"], accept="image/*")
            if media.status != 200:
                raise AssertionError("public featured image is unavailable")
            if not (response_header(media, "Content-Type") or "").startswith("image/"):
                raise AssertionError("featured image response is not an image")
            if "public" not in (response_header(media, "Cache-Control") or ""):
                raise AssertionError("featured image is missing public caching")
            decoded_index = urllib.parse.unquote(index_source)
            decoded_article = urllib.parse.unquote(article_source)
            if featured_image["url"] not in decoded_index:
                raise AssertionError("featured image is absent from initial index HTML")
            if featured_image["url"] not in decoded_article:
                raise AssertionError("featured image is absent from initial article HTML")
            matching_images = [
                alt
                for source, alt in article_html.images
                if featured_image["url"] in urllib.parse.unquote(source)
            ]
            if matching_images and featured_image["alt"] not in matching_images:
                raise AssertionError("featured image alt text does not match RankWin")

    index_links: set[str] = set()
    for link in index_html.links:
        if not link or link.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        joined = urllib.parse.urljoin(customer_blog_url + "/", link)
        parsed_link = urllib.parse.urlsplit(joined)
        if parsed_link.query or parsed_link.fragment:
            continue
        try:
            index_links.add(normalized_public_url(joined))
        except AssertionError:
            continue
    if expected_canonicals and not expected_canonicals.intersection(index_links):
        raise AssertionError("customer index has no crawlable RankWin article links")

    sitemap_url = f"{customer_blog_url.rstrip('/')}/sitemap.xml"
    sitemap_response = request(sitemap_url, accept="application/xml")
    assert_no_redirect(sitemap_response, sitemap_url, "customer sitemap")
    sitemap_root = parse_xml(sitemap_response, "sitemap")
    sitemap_kind, sitemap_urls = sitemap_locations(sitemap_root)
    if sitemap_kind != "urlset":
        raise AssertionError("customer RankWin sitemap must be a URL set")
    assert_site_scoped_urls(sitemap_urls, expected_canonicals, site, "sitemap")

    feed_url = f"{customer_blog_url.rstrip('/')}/feed.xml"
    feed_response = request(feed_url, accept="application/atom+xml")
    assert_no_redirect(feed_response, feed_url, "customer feed")
    feed_root = parse_xml(feed_response, "feed")
    feed_urls = feed_locations(feed_root)
    assert_site_scoped_urls(feed_urls, expected_canonicals, site, "feed")

    parsed_blog = urllib.parse.urlsplit(customer_blog_url)
    customer_origin = urllib.parse.urlunsplit(
        (parsed_blog.scheme, parsed_blog.netloc, "", "", "")
    )
    verify_sitemap_registration(customer_origin, sitemap_url, expected_canonicals)

    verify_removed_urls(args.removed_url, site, sitemap_urls | feed_urls | index_links)
    skipped = optional_isolation_checks(api_base, api_key, articles[0]["id"]) if articles else [
        "article content, ETag, media and cross-site isolation (no remaining published article)"
    ]
    if not args.removed_url:
        skipped.append("removed URL lifecycle (pass --removed-url after unpublishing a disposable article)")
    if site["blogPath"] == "/":
        skipped.append(
            "root-path route-collision audit (requires the customer framework's route manifest)"
        )
    skipped.append(
        "single GA4 network page-view (requires a consent-aware browser/GA DebugView run)"
    )

    print(
        f"RankWin CMS deterministic integration verified: {len(articles)} article(s), "
        "canonical HTML, sitemap, feed and registration; see unexercised controls below"
    )
    if skipped:
        print("External/operator controls not exercised by this HTTP verifier:")
        for item in skipped:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
