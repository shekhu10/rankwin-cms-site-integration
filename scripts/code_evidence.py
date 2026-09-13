"""Check that canonical code examples survive customer HTML delivery."""
from collections import Counter
from html.parser import HTMLParser


class CodeEvidenceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.pre = 0
        self.code = 0
        self.parts = []
        self.examples = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "pre":
            self.pre += 1
        if tag == "code" and self.pre:
            self.code += 1
            if self.code == 1:
                self.parts = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"} and self.hidden:
            self.hidden -= 1
            return
        if self.hidden:
            return
        if tag == "code" and self.code:
            self.code -= 1
            if not self.code:
                self.examples.append("".join(self.parts).replace("\r\n", "\n"))
        if tag == "pre" and self.pre:
            self.pre -= 1

    def handle_data(self, data):
        if self.code and not self.hidden:
            self.parts.append(data)


def assert_article_code(document, html):
    expected = Counter(
        block["code"].replace("\r\n", "\n")
        for block in document.get("blocks", [])
        if block.get("type") == "code"
    )
    parser = CodeEvidenceParser()
    parser.feed(html)
    missing = expected - Counter(parser.examples)
    if missing:
        raise AssertionError("canonical code example is missing or its whitespace changed in initial HTML")
