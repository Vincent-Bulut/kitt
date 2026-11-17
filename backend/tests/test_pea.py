"""Parsing of the Euronext PEA ETF list (no network)."""

from backend.api.pea import PeaEtf, find_new_isins, parse_number, parse_row, to_csv

ROW = [
    '<a href="/fr/product/etfs/FR0010315770-XPAR">Amundi MSCI World</a>',
    "CW8",
    '<div title="Euronext Paris">XPAR</div>',
    "-",
    "<span>EUR 512,34</span>",
    "+0,5%",
    "17/11/2026 17:35",
]


def test_parse_number_handles_french_format():
    assert parse_number("1 234,56") == 1234.56
    assert parse_number("1 234,5") == 1234.5
    assert parse_number("-") is None


def test_parse_row_extracts_listing_fields():
    etf = parse_row(ROW)
    assert etf is not None
    assert etf.isin == "FR0010315770"
    assert etf.mic == "XPAR"
    assert etf.symbol == "CW8"
    assert etf.market == "Euronext Paris"
    assert etf.currency == "EUR"
    assert etf.last_price == 512.34


def test_parse_row_rejects_rows_without_product_link():
    assert parse_row(["no link", "", "", "", "", "", ""]) is None


def _etf(isin, symbol, market, name="ETF"):
    return PeaEtf(
        name=name, isin=isin, symbol=symbol, mic="XPAR", market=market,
        currency="EUR", last_price=1.0, last_trade="", url="",
    )


def test_find_new_isins_merges_listings_and_skips_known():
    rows = [
        _etf("FR0000000001", "AAA", "Paris", name="b fund"),
        _etf("FR0000000001", "AAB", "Amsterdam", name="b fund"),
        _etf("FR0000000002", "BBB", "Paris", name="A fund"),
        _etf("FR0000000003", "CCC", "Paris"),
    ]
    new = find_new_isins(rows, known_isins={"FR0000000003"})

    assert [e["isin"] for e in new] == ["FR0000000002", "FR0000000001"]  # sorted by name, case-insensitive
    assert new[1]["symbols"] == ["AAA", "AAB"]
    assert new[1]["markets"] == ["Paris", "Amsterdam"]


def test_to_csv_has_header_and_one_line_per_row():
    csv_text = to_csv([_etf("FR0000000001", "AAA", "Paris")])
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("name,isin,symbol")
    assert len(lines) == 2
