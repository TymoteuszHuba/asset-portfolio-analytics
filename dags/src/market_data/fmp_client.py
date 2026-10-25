"""
FMP API Client Adapter implementing MarketDataProviderInterface contracts.
Handles network calls, rate limits, status code handling and payload normalization.
"""

from datetime import date
from decimal import Decimal
import logging
import os
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger("airflow.task")

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class MarketDataAPIError(Exception):
    """Base exception for Market Data API operations."""
    pass


class QuotaExceededError(MarketDataAPIError):
    """Raised when HTTP 429 (Rate limit / quota exceeded) is encountered."""
    pass


class FMPApiClient:
    """
    Client adapter for Financial Modeling Prep (FMP) Stable API.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("FMP_API_KEY", "demo")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Executes an HTTP GET request to FMP API with error resilience.
        """
        params = params or {}
        params["apikey"] = self.api_key
        url = f"{FMP_BASE_URL}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 429:
                logger.warning("FMP API quota limit reached (HTTP 429).")
                raise QuotaExceededError("Daily FMP API request quota exceeded.")
            elif response.status_code == 402:
                logger.warning("FMP API endpoint requires a paid subscription (HTTP 402).")
                raise MarketDataAPIError("HTTP 402: FMP API paid plan required for this resource.")
            elif response.status_code == 403:
                logger.error(f"FMP API authentication failed (HTTP 403). Server response: {response.text}")
                raise MarketDataAPIError(f"Invalid or forbidden FMP API Key (403): {response.text[:200]}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during FMP API request to {url}: {e}")
            raise MarketDataAPIError(f"HTTP request failed: {e}")

    def fetch_eod_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Retrieves End-of-Day closing prices for a ticker symbol between start_date and end_date.
        Uses FMP stable endpoint: /stable/historical-price-eod/full?symbol={symbol}
        """
        endpoint = "historical-price-eod/full"
        params = {
            "symbol": symbol.upper(),
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
        }
        
        try:
            data = self._get(endpoint, params)
            historical = data.get("historical", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            
            normalized_records = []
            for item in historical:
                price_date_str = item.get("date")
                close_price_val = item.get("close")
                
                if price_date_str and close_price_val is not None:
                    normalized_records.append({
                        "ticker": symbol.upper(),
                        "price_date": date.fromisoformat(price_date_str),
                        "close_price": Decimal(str(close_price_val)),
                        "currency": "USD",
                    })
                    
            return normalized_records
        except MarketDataAPIError as err:
            if "402" in str(err):
                logger.warning(f"FMP requires paid subscription for '{symbol}'. Falling back to Yahoo Finance public API...")
                return self._fetch_yahoo_prices_fallback(symbol, start_date, end_date)
            raise

    def _fetch_yahoo_prices_fallback(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Public fallback to Yahoo Finance chart API when FMP returns HTTP 402 (Subscription required).
        """
        import urllib.request
        import json
        from datetime import datetime, timezone
        
        # Yahoo expects tickers like VWCE.DE or BRK-B
        clean_symbol = symbol.replace(".", "-") if not symbol.endswith(".DE") else symbol
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_symbol}?interval=1d&range=1y"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data["chart"]["result"][0]
                timestamps = result.get("timestamp", [])
                closes = result["indicators"]["quote"][0].get("close", [])
                currency = result.get("meta", {}).get("currency", "USD")
                
                records = []
                for ts, close_val in zip(timestamps, closes):
                    if close_val is not None:
                        p_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                        if start_date <= p_date <= end_date:
                            records.append({
                                "ticker": symbol.upper(),
                                "price_date": p_date,
                                "close_price": Decimal(str(round(close_val, 4))),
                                "currency": currency,
                            })
                return records
        except Exception as exc:
            logger.error(f"Yahoo Finance fallback failed for '{symbol}': {exc}")
            return []

    def fetch_fx_rates(
        self,
        quote_currency: str,
        base_currency: str = "EUR",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves historical FX exchange rates for a currency pair (e.g. USDEUR).
        Falls back to Frankfurter API (European Central Bank data) if FMP requires a paid plan (402).
        """
        try:
            pair = f"{quote_currency.upper()}{base_currency.upper()}"
            endpoint = "historical-price-eod/full"
            params = {"symbol": pair}
            if start_date:
                params["from"] = start_date.strftime("%Y-%m-%d")
            if end_date:
                params["to"] = end_date.strftime("%Y-%m-%d")

            data = self._get(endpoint, params)
            historical = data.get("historical", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

            normalized_records = []
            for item in historical:
                rate_date_str = item.get("date")
                rate_val = item.get("close")

                if rate_date_str and rate_val is not None:
                    normalized_records.append({
                        "base_currency": base_currency.upper(),
                        "quote_currency": quote_currency.upper(),
                        "rate_date": date.fromisoformat(rate_date_str),
                        "rate": Decimal(str(rate_val)),
                    })
            if normalized_records:
                return normalized_records
        except MarketDataAPIError as e:
            logger.warning(f"FMP FX fetch failed ({e}). Attempting fallback to European Central Bank (Frankfurter API)...")

        # Fallback to Frankfurter API (ECB official daily EUR exchange rates - 100% Free)
        return self._fetch_fx_rates_frankfurter(quote_currency, base_currency, start_date, end_date)

    def _fetch_fx_rates_frankfurter(
        self,
        quote_currency: str,
        base_currency: str = "EUR",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Fallback method fetching official ECB daily exchange rates from Frankfurter API.
        """
        s_date = start_date or (date.today())
        e_date = end_date or date.today()
        url = f"https://api.frankfurter.app/{s_date.strftime('%Y-%m-%d')}..{e_date.strftime('%Y-%m-%d')}"
        params = {"from": quote_currency.upper(), "to": base_currency.upper()}

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            res_json = resp.json()
            rates_dict = res_json.get("rates", {})

            records = []
            for r_date_str, r_data in rates_dict.items():
                rate_val = r_data.get(base_currency.upper())
                if rate_val:
                    records.append({
                        "base_currency": base_currency.upper(),
                        "quote_currency": quote_currency.upper(),
                        "rate_date": date.fromisoformat(r_date_str),
                        "rate": Decimal(str(rate_val)),
                    })
            return records
        except Exception as ex:
            logger.error(f"Frankfurter FX fallback failed: {ex}")
            return []

    def fetch_stock_splits(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Retrieves corporate stock split history for a ticker symbol.
        Uses FMP stable endpoint: /stable/splits?symbol={symbol}
        """
        endpoint = "splits"
        params = {"symbol": symbol.upper()}
        data = self._get(endpoint, params)
        historical = data if isinstance(data, list) else data.get("historical", [])

        normalized_records = []
        for item in historical:
            split_date_str = item.get("date")
            num = item.get("numerator")
            den = item.get("denominator")

            if split_date_str and num and den:
                normalized_records.append({
                    "ticker": symbol.upper(),
                    "split_date": date.fromisoformat(split_date_str),
                    "numerator": int(num),
                    "denominator": int(den),
                })

        return normalized_records
