"""Check that structured tables survive customer HTML rendering."""
from html.parser import HTMLParser


def normalized(value: str) -> str:
    return " ".join(value.split())


def inline_text(nodes: list[dict]) -> str:
    return "".join(node.get("text", inline_text(node.get("children", []))) for node in nodes)


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.tables: list[list] = []
        self.table: list | None = None
        self.row: list | None = None
        self.cell: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "template"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = (tag, [])

    def handle_data(self, value: str) -> None:
        if not self.hidden and self.cell is not None:
            self.cell[1].append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "template"} and self.hidden:
            self.hidden -= 1
            return
        if self.hidden:
            return
        if tag in {"th", "td"} and self.cell is not None and self.row is not None:
            self.row.append((self.cell[0], normalized("".join(self.cell[1]))))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def assert_article_tables(document: dict, source: str) -> None:
    parser = TableParser()
    parser.feed(source)
    for block in document.get("blocks", []):
        if block.get("type") != "table":
            continue
        expected = []
        if block.get("header"):
            expected.append([("th", normalized(inline_text(cell["children"]))) for cell in block["header"]["cells"]])
        expected.extend([("td", normalized(inline_text(cell["children"]))) for cell in row["cells"]] for row in block["rows"])
        if expected not in parser.tables:
            raise AssertionError("article table headers, rows, or cells are absent from initial HTML")
        parser.tables.remove(expected)
