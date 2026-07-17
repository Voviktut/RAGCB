#!/usr/bin/env python3
"""Parse Avito listing descriptions that mention 1-3 years of experience.

The script works with static HTML returned by Avito: it discovers item links on
search result pages, opens each listing, extracts the title and description, and
keeps only descriptions containing a Russian 1-3 years experience phrase. By
default it creates an Excel .xlsx file where each row contains one description.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

DEFAULT_URL = (
    "https://www.avito.ru/moskva/predlozheniya_uslug/delovye_uslugi/"
    "buhgalteriya_finansy-ASgBAgICAkSYC7KfAZ4L9p8B"
)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
EXPERIENCE_RE = re.compile(
    r"(?i)(?:опыт(?:\s+работы)?[^\n\r.]{0,80})?"
    r"(?:1\s*[-–—]\s*3|от\s+1\s+до\s+3|1\s+до\s+3)\s*"
    r"(?:год(?:а)?|лет|г\.)"
)


@dataclass(frozen=True)
class Listing:
    url: str
    title: str
    description: str
    experience_match: str


class LinkParser(HTMLParser):
    """Collect candidate listing links from Avito search HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = dict(attrs)
        href = attr.get("href") or ""
        if re.search(r"_\d+(?:\?|$)", href) and not href.startswith("#"):
            self.links.append(href)


class TextBlockParser(HTMLParser):
    """Extract visible text from selected Avito listing blocks."""

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.description_parts: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        marker = ""
        itemprop = attr.get("itemprop", "")
        data_marker = attr.get("data-marker", "")
        if tag == "h1" or itemprop == "name" or data_marker == "item-view/title-info":
            marker = "title"
        elif itemprop == "description" or data_marker in {
            "item-view/item-description",
            "item-view/item-description-text",
        }:
            marker = "description"
        self._stack.append(marker or (self._stack[-1] if self._stack else ""))

    def handle_endtag(self, tag: str) -> None:
        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        text = clean_text(data)
        if not text:
            return
        if self._stack[-1] == "title":
            self.title_parts.append(text)
        elif self._stack[-1] == "description":
            self.description_parts.append(text)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["p"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def fetch(url: str, user_agent: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": user_agent, "Accept-Language": "ru-RU,ru;q=0.9"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-provided scraper URL
        return response.read().decode("utf-8", errors="replace")


def listing_links(html: str, base_url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    seen: set[str] = set()
    links: list[str] = []
    for href in parser.links:
        absolute = urljoin(base_url, href.split("?")[0])
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    return links


def extract_listing(html: str, url: str) -> Listing | None:
    parser = TextBlockParser()
    parser.feed(html)
    title = clean_text(" ".join(parser.title_parts))
    description = clean_text(" ".join(parser.description_parts))
    if not description:
        meta = re.search(r'<meta[^>]+(?:name|property)=["\']description["\'][^>]+content=["\']([^"\']+)', html)
        description = clean_text(meta.group(1)) if meta else ""
    match = EXPERIENCE_RE.search(description)
    if not match:
        return None
    return Listing(url=url, title=title, description=description, experience_match=match.group(0))


def parse(url: str, pages: int, delay: float, user_agent: str, timeout: int) -> Iterable[Listing]:
    visited: set[str] = set()
    for page in range(1, pages + 1):
        search_url = page_url(url, page)
        search_html = fetch(search_url, user_agent, timeout)
        for link in listing_links(search_html, search_url):
            if link in visited:
                continue
            visited.add(link)
            time.sleep(delay)
            try:
                listing_html = fetch(link, user_agent, timeout)
            except Exception as exc:  # keep scraping other cards
                print(f"Skipping {link}: {exc}", file=sys.stderr)
                continue
            listing = extract_listing(listing_html, link)
            if listing:
                yield listing
        time.sleep(delay)


def inline_string_cell(row: int, column: str, value: str) -> str:
    safe_value = escape(value, quote=False)
    return f'<c r="{column}{row}" t="inlineStr"><is><t>{safe_value}</t></is></c>'


def write_xlsx(listings: list[Listing], output_path: str) -> None:
    """Write an Excel file with one listing per row and description in column A."""
    rows = [
        '<row r="1">'
        + inline_string_cell(1, "A", "description")
        + inline_string_cell(1, "B", "title")
        + inline_string_cell(1, "C", "url")
        + inline_string_cell(1, "D", "experience_match")
        + "</row>"
    ]
    for index, listing in enumerate(listings, start=2):
        rows.append(
            f'<row r="{index}">'
            + inline_string_cell(index, "A", listing.description)
            + inline_string_cell(index, "B", listing.title)
            + inline_string_cell(index, "C", listing.url)
            + inline_string_cell(index, "D", listing.experience_match)
            + "</row>"
        )

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        '<cols><col min="1" max="1" width="100" customWidth="1"/></cols>'
        f'<sheetData>{"".join(rows)}</sheetData>'
        '</worksheet>'
    )
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Avito parser</Application></Properties>""",
        "docProps/core.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Avito parser</dc:creator><cp:lastModifiedBy>Avito parser</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified></cp:coreProperties>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="descriptions" sheetId="1" r:id="rId1"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>""",
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        for name, content in files.items():
            workbook.writestr(name, content)


def write_output(listings: list[Listing], output_path: str) -> None:
    suffix = Path(output_path).suffix.lower()
    if suffix == ".xlsx":
        write_xlsx(listings, output_path)
        return
    if suffix == ".json":
        with open(output_path, "w", encoding="utf-8") as output_file:
            json.dump([asdict(item) for item in listings], output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
        return
    raise ValueError("Output file must end with .xlsx or .json")


def main() -> int:
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--url", default=DEFAULT_URL, help="Avito search/category URL to parse")
    arg_parser.add_argument("--pages", type=int, default=1, help="Number of result pages to scan")
    arg_parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds")
    arg_parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    arg_parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="HTTP User-Agent header")
    arg_parser.add_argument("--output", default="descriptions.xlsx", help="Path for .xlsx or .json output")
    args = arg_parser.parse_args()

    listings = list(parse(args.url, args.pages, args.delay, args.user_agent, args.timeout))
    write_output(listings, args.output)
    print(f"Saved {len(listings)} matching listings to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
