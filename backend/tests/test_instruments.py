import pytest

from backend.api.analytics.instruments import is_leveraged_or_inverse


@pytest.mark.parametrize(
    "name",
    [
        "Amundi CAC 40 Daily (-2x) Inverse UCITS ETF Acc",
        "Amundi CAC 40 Daily (-1x) Inverse UCITS ETF Acc",
        "Amundi CAC 40 Daily (2x) Leveraged UCITS ETF Acc",
        "Amundi LevDax Daily (2x) leveraged UCITS ETF Acc",
        "Amundi MSCI World (2x) Leveraged UCITS ETF Acc",
        "Xtrackers S&P 500 2x Inverse Daily Swap UCITS ETF",
        "WisdomTree NASDAQ 100 3x Daily Leveraged",
    ],
)
def test_detects_leveraged_and_inverse_products(name):
    assert is_leveraged_or_inverse(name)


@pytest.mark.parametrize(
    "name",
    [
        "iShares € Short Term Swap PEA ETF",
        "iShares € Ultrashort Bond UCITS ETF",
        "Amundi PEA Japon (TOPIX) UCITS ETF EUR Hedged Acc",
        "Amundi MSCI World UCITS ETF Acc",
        "Xtrackers II EUR Overnight Rate Swap UCITS ETF",
        None,
        "",
    ],
)
def test_does_not_flag_regular_funds(name):
    assert not is_leveraged_or_inverse(name)
