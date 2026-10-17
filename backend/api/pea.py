"""Scrape PEA-eligible ETFs from https://live.euronext.com/fr/products/etfs/list.

The list page is rendered client-side by DataTables. Its rows come from a
JSON endpoint (``drupalSettings.jsongateway``) that accepts the same filters
as the page sidebar; ``args[pea]=Yes`` returns only PEA-eligible ETFs.
"""

import csv
import html
import io
import json
import re
import time
from dataclasses import asdict, dataclass, fields

import requests

BASE_URL = "https://live.euronext.com"
DEFAULT_ETF_LIST_URL = f"{BASE_URL}/fr/products/etfs/list"
PAGE_SIZE = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


@dataclass
class PeaEtf:
    name: str
    isin: str
    symbol: str
    mic: str
    market: str
    currency: str | None
    last_price: float | None
    last_trade: str
    url: str


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_number(value: str) -> float | None:
    """Parse a French-formatted number such as '1 234,56'."""
    cleaned = re.sub(r"[\s  ]", "", value).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def discover_gateway_url(session: requests.Session, list_url: str) -> str:
    """Read the JSON data endpoint from the page's drupalSettings."""
    response = session.get(list_url, timeout=30)
    response.raise_for_status()

    match = re.search(
        r'data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>',
        response.text,
        flags=re.S,
    )
    if not match:
        raise RuntimeError("drupalSettings JSON not found on the list page.")

    gateway = json.loads(match.group(1)).get("jsongateway")
    if not gateway:
        raise RuntimeError("'jsongateway' missing from drupalSettings.")

    return BASE_URL + gateway


def fetch_page(session: requests.Session, gateway_url: str, referer: str, start: int, length: int) -> dict:
    payload = {
        "draw": 1,
        "start": start,
        "length": length,
        "iDisplayStart": start,
        "iDisplayLength": length,
        "args[pea]": "Yes",
    }
    response = session.post(
        gateway_url,
        data=payload,
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": referer},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def parse_row(row: list[str]) -> PeaEtf | None:
    """Parse one DataTables row.

    Columns: name/link, symbol, market, bid/ask, last price, % change,
    last trade time.
    """
    link = re.search(r'href="([^"]+)"', row[0])
    if not link:
        return None

    href = link.group(1)
    isin_mic = re.search(r"/product/etfs/([A-Z0-9]{12})-([A-Z0-9]+)", href, flags=re.I)
    if not isin_mic:
        return None

    market_title = re.search(r'title="([^"]+)"', row[2])
    price_text = strip_tags(row[4])
    price_match = re.match(r"([A-Z]{3})\s+(.+)", price_text)

    return PeaEtf(
        name=strip_tags(row[0]),
        isin=isin_mic.group(1).upper(),
        symbol=strip_tags(row[1]),
        mic=isin_mic.group(2).upper(),
        market=html.unescape(market_title.group(1)) if market_title else strip_tags(row[2]),
        currency=price_match.group(1) if price_match else None,
        last_price=parse_number(price_match.group(2)) if price_match else None,
        last_trade=strip_tags(row[6]) if len(row) > 6 else "",
        url=f"{BASE_URL}{href}/market-information",
    )


def scrape_pea_etfs(list_url: str = DEFAULT_ETF_LIST_URL, delay_seconds: float = 0.5) -> list[PeaEtf]:
    session = requests.Session()
    session.headers.update(HEADERS)

    gateway_url = discover_gateway_url(session, list_url)

    results: list[PeaEtf] = []
    start = 0
    total = None

    while total is None or start < total:
        data = fetch_page(session, gateway_url, list_url, start, PAGE_SIZE)
        total = int(data.get("iTotalDisplayRecords", 0))
        rows = data.get("aaData", [])
        if not rows:
            break

        results.extend(etf for etf in map(parse_row, rows) if etf is not None)
        start += len(rows)
        if start < total:
            time.sleep(delay_seconds)

    return results


def to_csv(rows: list[PeaEtf]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[f.name for f in fields(PeaEtf)])
    writer.writeheader()
    writer.writerows(asdict(row) for row in rows)
    return buffer.getvalue()
