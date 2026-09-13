"""Visible pagination links and article-scoped media in server-rendered indexes."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
HIDDEN_TAGS = {"script", "style", "template", "noscript"}


@dataclass
class IndexNode:
    tag: str
    attrs: dict[str, str]
    hidden: bool
    pagination: bool
    links: list[str] = field(default_factory=list)
    images: list[tuple[str, str]] = field(default_factory=list)


class IndexEvidenceParser(HTMLParser):
    def __init__(self, resolved_streams: set[str] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[IndexNode] = []
        self.cards: list[IndexNode] = []
        self.links: list[str] = []
        self.pagination_links: list[str] = []
        self.resolved_streams = resolved_streams or set()
        self.stream_containers: set[str] = set()
        self.stream_templates: dict[str, tuple[set[str], bool]] = {}
        self.stream_completions: list[tuple[str, str]] = []
        self._script_parts: list[str] | None = None

    @staticmethod
    def is_stream_container(tag: str, values: dict[str, str]) -> bool:
        return tag == "div" and "hidden" in values and bool(re.fullmatch(r"S:[a-zA-Z0-9]+", values.get("id", "")))

    @staticmethod
    def otherwise_hidden(tag: str, values: dict[str, str]) -> bool:
        return tag in HIDDEN_TAGS or values.get("aria-hidden", "").lower() == "true" or bool(
            re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", values.get("style", ""), re.I)
        )

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        stream_container = self.is_stream_container(tag, values)
        if stream_container:
            self.stream_containers.add(values["id"])
        if tag == "template" and re.fullmatch(r"[BP]:[a-zA-Z0-9]+", values.get("id", "")):
            required = {node.attrs["id"] for node in self.stack if self.is_stream_container(node.tag, node.attrs)}
            hidden_parent = any(self.otherwise_hidden(node.tag, node.attrs) or (
                "hidden" in node.attrs and not self.is_stream_container(node.tag, node.attrs)
            ) for node in self.stack)
            self.stream_templates[values["id"]] = (required, hidden_parent)
        if tag == "script" and values.get("type", "").lower() in {"", "module", "text/javascript", "application/javascript"}:
            self._script_parts = []
        hidden = (
            bool(self.stack and self.stack[-1].hidden)
            or self.otherwise_hidden(tag, values)
            or ("hidden" in values and not (stream_container and values["id"] in self.resolved_streams))
        )
        pagination = bool(self.stack and self.stack[-1].pagination) or (
            (tag == "nav" or values.get("role") == "navigation")
            and bool(re.search(r"\bpaginat(?:ion|ed)\b|\bpages\b", values.get("aria-label", ""), re.I))
        ) or bool(re.search(r"(?:^|[\s_-])pagination(?:$|[\s_-])", values.get("class", ""), re.I))
        node = IndexNode(tag, values, hidden, pagination)
        # A common card layout wraps <article> in its canonical <a>.
        if not hidden:
            node.links.extend(parent.attrs["href"] for parent in self.stack if parent.tag == "a" and parent.attrs.get("href"))
        if tag not in VOID_TAGS:
            self.stack.append(node)
        if hidden:
            return
        href = values.get("href")
        relations = values.get("rel", "").lower().split()
        if tag == "a" and href:
            self.links.append(href)
            for parent in self.stack:
                parent.links.append(href)
        if tag in {"a", "link"} and href and (
            "next" in relations or "prev" in relations or (tag == "a" and pagination)
        ):
            self.pagination_links.append(href)
        if tag == "img" and values.get("src"):
            for parent in self.stack:
                parent.images.append((values["src"], values.get("alt", "")))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script_parts is not None:
            script = "".join(self._script_parts)
            self.stream_completions.extend((source, target) for target, source in re.findall(r'(?:^|[;}])\s*\$RC\("(B:[a-zA-Z0-9]+)","(S:[a-zA-Z0-9]+)"\)', script))
            self.stream_completions.extend(re.findall(r'(?:^|[;}])\s*\$RS\("(S:[a-zA-Z0-9]+)","(P:[a-zA-Z0-9]+)"\)', script))
            self._script_parts = None
        matching = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i].tag == tag), None)
        if matching is None:
            return
        for node in self.stack[matching:]:
            is_card = node.tag in {"a", "article", "li"} or node.attrs.get("role") in {"article", "listitem"} or re.search(
                r"(?:^|[\s_-])(?:card|post|entry)(?:$|[\s_-])", node.attrs.get("class", ""), re.I
            )
            if is_card and not node.hidden:
                self.cards.append(node)
        del self.stack[matching:]

    def handle_data(self, data: str) -> None:
        if self._script_parts is not None:
            self._script_parts.append(data)


def parse_index_evidence(source: str) -> IndexEvidenceParser:
    probe = IndexEvidenceParser()
    probe.feed(source)
    resolved: set[str] = set()
    # React's completed streaming payloads are temporary hidden transports.
    # Resolve only literal completion calls with real destination placeholders;
    # never execute page JavaScript or count an unresolved/otherwise hidden tree.
    while True:
        previous = len(resolved)
        for source_id, target_id in probe.stream_completions:
            destination = probe.stream_templates.get(target_id)
            if source_id in probe.stream_containers and destination:
                required, hidden_parent = destination
                if not hidden_parent and required.issubset(resolved):
                    resolved.add(source_id)
        if len(resolved) == previous:
            break
    if not resolved:
        return probe
    result = IndexEvidenceParser(resolved)
    result.feed(source)
    return result


def image_source_matches(source: str, expected: str) -> bool:
    return source == expected or expected in urllib.parse.parse_qs(
        urllib.parse.urlsplit(source).query
    ).get("url", [])
