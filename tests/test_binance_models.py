from datetime import UTC, datetime

import pytest

from crypto_flow_bot_v2.binance.models import Candlestick, FundingRate, datetime_from_millis

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_datetime_from_millis_returns_aware_utc_datetime() -> None:
    result = datetime_from_millis(1_704_067_200_000)

    assert result.tzinfo is UTC
    assert result.year == 2024


def test_candlestick_rejects_invalid_high_low_range() -> None:
    with pytest.raises(ValueError, match="high"):
        Candlestick(
            symbol="BTCUSDT",
            interval="15m",
            open_time=NOW,
            close_time=NOW,
            open=100.0,
            high=99.0,
            low=101.0,
            close=100.0,
            volume=1.0,
            quote_volume=100.0,
            trade_count=1,
            taker_buy_base_volume=0.5,
            taker_buy_quote_volume=50.0,
        )


def test_funding_rate_allows_negative_funding_rate() -> None:
    funding = FundingRate(
        symbol="BTCUSDT",
        funding_time=NOW,
        funding_rate=-0.0002,
        mark_price=100_000.0,
    )

    assert funding.funding_rate == -0.0002
