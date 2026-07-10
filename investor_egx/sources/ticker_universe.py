from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Any

import pandas as pd

from investor_egx.config import Settings
from investor_egx.http_utils import RateLimiter, build_retrying_session


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class TickerUniverseCollector:
    settings: Settings

    def __post_init__(self) -> None:
        self.session = build_retrying_session(
            user_agent=self.settings.user_agent,
            max_retries=self.settings.max_retries,
        )
        self.limiter = RateLimiter(self.settings.min_request_interval_sec)

    def collect(self) -> list[dict]:
        merged = {}
        for batch in (
            self._from_tradingview_screener(),
            self._from_investpy(),
            self._from_yahoo_search(),
        ):
            for row in batch:
                key = row.get("isin") or row.get("egx_symbol")
                if not key:
                    continue
                if key not in merged:
                    merged[key] = row
                    continue
                merged[key] = self._merge_record(merged[key], row)
        return sorted(merged.values(), key=lambda x: (x.get("egx_symbol") or "", x.get("company_name") or ""))

    def _merge_record(self, lhs: dict, rhs: dict) -> dict:
        merged = dict(lhs)
        for k, v in rhs.items():
            if k not in merged or merged[k] in (None, "", 0):
                merged[k] = v
                continue
            if k == "source":
                merged[k] = f"{lhs.get('source','')},{rhs.get('source','')}".strip(",")
        return merged

    def _from_tradingview_screener(self) -> list[dict]:
        try:
            from tradingview_screener import Query
        except Exception:
            return []

        try:
            _, df = (
                Query()
                .set_markets("egypt")
                .select(
                    "name",
                    "description",
                    "exchange",
                    "currency",
                    "sector",
                    "industry",
                    "type",
                )
                .limit(5000)
                .get_scanner_data()
            )
        except Exception:
            return []

        records: list[dict] = []
        for _, row in df.iterrows():
            raw_symbol = _safe_text(row.get("name"))
            if not raw_symbol:
                continue
            egx_symbol = raw_symbol.split(":")[-1].strip().upper()
            records.append(
                {
                    "egx_symbol": egx_symbol,
                    "isin": None,
                    "yahoo_symbol": None,
                    "investpy_symbol": egx_symbol,
                    "tradingview_symbol": raw_symbol,
                    "company_name": _safe_text(row.get("description")),
                    "sector": _safe_text(row.get("sector")),
                    "industry": _safe_text(row.get("industry")),
                    "currency": _safe_text(row.get("currency")) or "EGP",
                    "exchange_code": "XCAI",
                    "is_active": 1,
                    "source": "tradingview_screener",
                }
            )
        return records

    def _from_investpy(self) -> list[dict]:
        try:
            import investpy
        except Exception:
            return []

        try:
            df = investpy.stocks.get_stocks(country="egypt")
        except Exception:
            return []

        if not isinstance(df, pd.DataFrame):
            return []

        records: list[dict] = []
        for _, row in df.iterrows():
            symbol = _safe_text(row.get("symbol"))
            if not symbol:
                continue
            records.append(
                {
                    "egx_symbol": symbol.upper(),
                    "isin": _safe_text(row.get("isin")),
                    "yahoo_symbol": None,
                    "investpy_symbol": symbol.upper(),
                    "tradingview_symbol": None,
                    "company_name": _safe_text(row.get("name")) or _safe_text(row.get("full_name")),
                    "sector": None,
                    "industry": None,
                    "currency": _safe_text(row.get("currency")) or "EGP",
                    "exchange_code": "XCAI",
                    "is_active": 1,
                    "source": "investpy",
                }
            )
        return records

    def _from_yahoo_search(self) -> list[dict]:
        prefixes = [f"EGS{ch}" for ch in (list(string.digits) + list(string.ascii_uppercase))]
        records: list[dict] = []
        seen_symbols: set[str] = set()
        for prefix in prefixes:
            self.limiter.wait()
            try:
                response = self.session.get(
                    "https://query2.finance.yahoo.com/v1/finance/search",
                    params={"q": prefix, "quotesCount": 100, "newsCount": 0},
                    timeout=self.settings.request_timeout_sec,
                )
                if response.status_code == 429:
                    continue
                response.raise_for_status()
                payload = response.json()
            except Exception:
                continue
            for quote in payload.get("quotes", []):
                if str(quote.get("exchange", "")).upper() != "CAI":
                    continue
                yahoo_symbol = _safe_text(quote.get("symbol"))
                if not yahoo_symbol or yahoo_symbol in seen_symbols:
                    continue
                if not yahoo_symbol.endswith(".CA"):
                    continue
                seen_symbols.add(yahoo_symbol)
                isin = yahoo_symbol.split(".")[0]
                records.append(
                    {
                        "egx_symbol": isin,
                        "isin": isin,
                        "yahoo_symbol": yahoo_symbol,
                        "investpy_symbol": None,
                        "tradingview_symbol": None,
                        "company_name": _safe_text(quote.get("shortname")) or _safe_text(quote.get("longname")),
                        "sector": None,
                        "industry": None,
                        "currency": _safe_text(quote.get("currency")) or "EGP",
                        "exchange_code": "XCAI",
                        "is_active": 1,
                        "source": "yahoo_search",
                    }
                )
        return records
