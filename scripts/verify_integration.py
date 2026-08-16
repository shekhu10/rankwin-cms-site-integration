#!/usr/bin/env python3
"""Verify the public RankWin CMS API and optional customer HTML delivery."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def request(
    url: str,
    *,
    api_key: str | None = None,
    etag: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    headers = {"User-Agent": "rankwin-cms-integration-verifier/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if etag:
        headers["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=15
        ) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()
    except Exception as error:  # Never include the capability-bearing URL.
        raise RuntimeError(f"request failed: {type(error).__name__}") from error


def json_response(url: str, api_key: str) -> tuple[dict, dict[str, str]]:
    status, headers, body = request(url, api_key=api_key)
    if status != 200:
        raise AssertionError(f"expected 200 JSON, received {status}")
    if "application/json" not in headers.get("Content-Type", ""):
        raise AssertionError("response is not application/json")
    return json.loads(body), headers


def response_header(headers: dict[str, str], name: str) -> str | None:
    expected = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == expected),
        None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--customer-blog-url")
    args = parser.parse_args()
    api_base = args.api_base.rstrip("/")
    api_key = os.environ.get("RANKWIN_CMS_API_KEY", "")
    if not api_key:
        raise AssertionError(
            "RANKWIN_CMS_API_KEY is missing from the server environment"
        )

    unauthenticated_status, _, _ = request(f"{api_base}/articles?limit=1")
    assert unauthenticated_status == 401, (
        "unauthenticated list must return 401, received "
        f"{unauthenticated_status}"
    )
    wrong_status, _, _ = request(
        f"{api_base}/articles?limit=1",
        api_key=f"rwcms_live_{'A' * 43}",
    )
    assert wrong_status == 401, f"wrong-site/invalid key returned {wrong_status}"

    page, _ = json_response(f"{api_base}/articles?limit=20", api_key)
    assert page.get("apiVersion") == "cms.v1", "unexpected API version"
    articles = page.get("articles")
    assert isinstance(articles, list) and articles, "no published articles"
    summary = articles[0]
    for field in ("id", "slug", "title", "metaDescription", "canonicalUrl"):
        assert summary.get(field), f"list summary missing {field}"
    featured_image = summary.get("featuredImage")
    assert featured_image is None or (
        isinstance(featured_image, dict)
        and featured_image.get("id")
        and featured_image.get("alt")
        and isinstance(featured_image.get("url"), str)
        and featured_image["url"].startswith("https://")
    ), "list summary has an invalid featuredImage"

    article_id = urllib.parse.quote(summary["id"], safe="")
    detail, headers = json_response(
        f"{api_base}/articles/by-id/{article_id}", api_key
    )
    article = detail.get("article", {})
    assert article.get("id") == summary["id"], "ID detail mismatch"
    assert article.get("documentId"), "detail missing documentId"
    assert article.get("html"), "detail missing rendered HTML"
    assert article.get("seo"), "detail missing SEO projection"
    assert article.get("jsonLd"), "detail missing structured data"
    assert article.get("featuredImage") == featured_image, (
        "list/detail featuredImage mismatch"
    )
    blocks = article.get("document", {}).get("blocks")
    assert isinstance(blocks, list) and blocks, "document has no blocks"
    block_ids = [block.get("id") for block in blocks]
    assert all(block_ids), "a block is missing id"
    assert len(block_ids) == len(set(block_ids)), "block IDs are not unique"

    if featured_image:
        media_status, media_headers, media_body = request(featured_image["url"])
        assert media_status == 200, (
            f"public featured image returned {media_status}"
        )
        assert (response_header(media_headers, "Content-Type") or "").startswith("image/"), (
            "featured image response is not an image"
        )
        assert "immutable" in (
            response_header(media_headers, "Cache-Control") or ""
        ), "featured image is missing immutable caching"
        assert media_body, "featured image response is empty"

    etag = response_header(headers, "ETag")
    assert etag, "detail has no ETag"
    status, _, _ = request(
        f"{api_base}/articles/by-id/{article_id}", api_key=api_key, etag=etag
    )
    assert status == 304, f"conditional detail expected 304, received {status}"

    if args.customer_blog_url:
        blog = args.customer_blog_url.rstrip("/")
        slug = urllib.parse.quote(summary["slug"], safe="")
        for label, url in (("index", blog), ("article", f"{blog}/{slug}")):
            status, response_headers, body = request(url)
            assert status == 200, f"customer {label} returned {status}"
            assert "text/html" in response_headers.get("Content-Type", ""), (
                f"customer {label} is not HTML"
            )
            source = body.decode("utf-8", errors="replace")
            decoded_source = urllib.parse.unquote(source)
            assert "rel=\"canonical\"" in source or "rel='canonical'" in source, (
                f"customer {label} has no canonical"
            )
            if label == "article":
                assert article["title"] in source, "article title absent from HTML"
                assert "application/ld+json" in source, "JSON-LD absent from HTML"
            if featured_image:
                assert featured_image["url"] in decoded_source, (
                    f"featured image absent from initial customer {label} HTML"
                )

    print("RankWin CMS integration verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
