"""
Unit tests for Market Data FMPApiClient and Incremental Sync Engine.
Uses requests_mock for 100% offline API testing without consuming FMP API quota.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest
import requests_mock

from src.market_data.fmp_client import FMPApiClient, MarketDataAPIError


@pytest.fixture
def fmp_client():
    return FMPApiClient(api_key="test_dummy_key")


def test_fmp_client_fetch_eod_prices(fmp_client):
    """
    Verifies that fetch_eod_prices correctly parses FMP stable JSON response.
    """
    mock_url = "https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&from=2026-05-01&to=2026-05-05&apikey=test_dummy_key"
    mock_payload = {
        "symbol": "AAPL",
        "historical": [
            {"date": "2026-05-05", "close": 185.50},
            {"date": "2026-05-02", "close": 182.30}
        ]
    }

    with requests_mock.Mocker() as m:
        m.get(mock_url, json=mock_payload, status_code=200)

        prices = fmp_client.fetch_eod_prices(
            symbol="AAPL",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 5)
        )

        assert len(prices) == 2
        assert prices[0]["ticker"] == "AAPL"
        assert prices[0]["price_date"] == date(2026, 5, 5)
        assert prices[0]["close_price"] == Decimal("185.50")
        assert prices[0]["currency"] == "USD"


def test_fmp_client_fetch_fx_rates_fallback(fmp_client):
    """
    Verifies that HTTP 402 Payment Required on FMP triggers automatic fallback to Frankfurter API (ECB).
    """
    fmp_url = "https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=USDEUR&from=2026-05-01&to=2026-05-05&apikey=test_dummy_key"
    frankfurter_url = "https://api.frankfurter.app/2026-05-01..2026-05-05?from=USD&to=EUR"
    
    frankfurter_payload = {
        "amount": 1.0,
        "base": "USD",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "rates": {
            "2026-05-02": {"EUR": 0.9250},
            "2026-05-05": {"EUR": 0.9280}
        }
    }

    with requests_mock.Mocker() as m:
        # 1. FMP returns 402 Payment Required
        m.get(fmp_url, status_code=402, text='{"Error Message": "Paid tier required"}')
        
        # 2. Fallback to Frankfurter API returns 200 OK
        m.get(frankfurter_url, json=frankfurter_payload, status_code=200)

        rates = fmp_client.fetch_fx_rates(
            quote_currency="USD",
            base_currency="EUR",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 5)
        )

        assert len(rates) == 2
        assert rates[0]["base_currency"] == "EUR"
        assert rates[0]["quote_currency"] == "USD"
        assert rates[0]["rate_date"] == date(2026, 5, 2)
        assert rates[0]["rate"] == Decimal("0.9250")


def test_fmp_client_http_429_quota_exceeded(fmp_client):
    """
    Verifies that HTTP 429 raises QuotaExceededError.
    """
    mock_url = "https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&from=2026-05-01&to=2026-05-05&apikey=test_dummy_key"

    with requests_mock.Mocker() as m:
        m.get(mock_url, status_code=429, text='Limit Exceeded')

        with pytest.raises(MarketDataAPIError):
            fmp_client.fetch_eod_prices("AAPL", date(2026, 5, 1), date(2026, 5, 5))
