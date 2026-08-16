#!/usr/bin/env python3
"""Discover the authenticated RankWin CMS hostname and customer blog path."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


BLOG_SEGMENT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._~-]{0,79})?$")
HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def configured_value(argument: str | None, environment_name: str) -> str:
    value = (argument or os.environ.get(environment_name, "")).strip()
    if not value:
        raise RuntimeError(
            f"{environment_name} is missing; set it in the customer secret environment"
        )
    return value


def validate_api_base(value: str) -> str:
    base = value.rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "::1",
        "localhost",
    }
    if (parsed.scheme != "https" and not local_http) or not parsed.netloc:
        raise RuntimeError("RANKWIN_CMS_API_BASE must be an HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(
            "RANKWIN_CMS_API_BASE must not contain credentials, query, or fragment data"
        )
    return base


def validate_blog_path(value: object) -> str:
    if value == "/":
        return "/"
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.endswith("/")
    ):
        raise RuntimeError("RankWin returned an invalid site.blogPath")
    segments = value[1:].split("/")
    if (
        len(value) > 240
        or any(segment in {"", ".", ".."} for segment in segments)
        or any(not BLOG_SEGMENT.fullmatch(segment) for segment in segments)
    ):
        raise RuntimeError("RankWin returned an invalid site.blogPath")
    return value


def parse_site(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise RuntimeError("RankWin site discovery returned an unexpected API contract")
    if payload.get("apiVersion") != "cms.v1" or not isinstance(
        payload.get("site"), dict
    ):
        raise RuntimeError("RankWin site discovery returned an unexpected API contract")

    site = payload["site"]
    host = site.get("host")
    labels = host.split(".") if isinstance(host, str) else []
    if not isinstance(host, str) or (
        not host
        or host != host.lower()
        or len(host) > 253
        or len(labels) < 2
        or any(not HOST_LABEL.fullmatch(label) for label in labels)
    ):
        raise RuntimeError("RankWin returned an invalid site.host")
    blog_path = validate_blog_path(site.get("blogPath"))
    suffix = "" if blog_path == "/" else blog_path
    return {
        "apiVersion": "cms.v1",
        "host": host,
        "blogPath": blog_path,
        "customerBlogUrl": f"https://{host}{suffix}/",
    }


def discover(api_base: str, api_key: str) -> dict[str, str]:
    request = urllib.request.Request(
        f"{api_base}/articles?limit=1",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "rankwin-cms-site-discovery/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise RuntimeError(
                "RankWin rejected the delivery API key (401); replace the key "
                "or restore the paid entitlement"
            ) from error
        raise RuntimeError(f"RankWin site discovery returned HTTP {error.code}") from error
    except Exception as error:
        raise RuntimeError(
            f"RankWin site discovery failed: {type(error).__name__}"
        ) from error

    if status != 200 or "application/json" not in content_type:
        raise RuntimeError("RankWin site discovery did not return cms.v1 JSON")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("RankWin site discovery returned invalid JSON") from error
    return parse_site(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--api-base",
        help="defaults to RANKWIN_CMS_API_BASE; never pass the API key as an argument",
    )
    args = parser.parse_args()
    api_base = validate_api_base(
        configured_value(args.api_base, "RANKWIN_CMS_API_BASE")
    )
    api_key = configured_value(None, "RANKWIN_CMS_API_KEY")
    print(json.dumps(discover(api_base, api_key), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Site discovery failed: {error}", file=sys.stderr)
        raise SystemExit(1)
