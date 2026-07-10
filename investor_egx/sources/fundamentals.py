from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from investor_egx.config import Settings
from investor_egx.http_utils import RateLimiter


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


@dataclass
class FundamentalsSource:
    settings: Settings
    _tv_snapshot: pd.DataFrame | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.limiter = RateLimiter(self.settings.min_request_interval_sec)

    def fetch(
        self,
        egx_symbol: str,
        yahoo_symbol: str | None = None,
        tradingview_symbol: str | None = None,
    ) -> dict:
        as_of_date = date.today().isoformat()
        yahoo_payload = self._from_yfinance(yahoo_symbol) if yahoo_symbol else {}
        tv_payload = self._from_tradingview(egx_symbol, tradingview_symbol)

        merged = {
            "as_of_date": as_of_date,
            "pe_ratio": tv_payload.get("pe_ratio") or yahoo_payload.get("pe_ratio"),
            "eps": tv_payload.get("eps") or yahoo_payload.get("eps"),
            "market_cap": tv_payload.get("market_cap") or yahoo_payload.get("market_cap"),
            "dividend_yield": tv_payload.get("dividend_yield") or yahoo_payload.get("dividend_yield"),
            "pb_ratio": tv_payload.get("pb_ratio") or yahoo_payload.get("pb_ratio"),
            "ps_ratio": tv_payload.get("ps_ratio") or yahoo_payload.get("ps_ratio"),
            "roe": tv_payload.get("roe") or yahoo_payload.get("roe"),
            "roa": tv_payload.get("roa") or yahoo_payload.get("roa"),
            "debt_to_equity": tv_payload.get("debt_to_equity") or yahoo_payload.get("debt_to_equity"),
            "current_ratio": tv_payload.get("current_ratio") or yahoo_payload.get("current_ratio"),
            "quick_ratio": tv_payload.get("quick_ratio") or yahoo_payload.get("quick_ratio"),
            "revenue_ttm": tv_payload.get("revenue_ttm") or yahoo_payload.get("revenue_ttm"),
            "net_income_ttm": tv_payload.get("net_income_ttm") or yahoo_payload.get("net_income_ttm"),
            "free_cash_flow_ttm": tv_payload.get("free_cash_flow_ttm") or yahoo_payload.get("free_cash_flow_ttm"),
            "source": "tradingview_screener+yfinance",
            "raw_json": {"tradingview": tv_payload.get("raw"), "yfinance": yahoo_payload.get("raw")},
        }
        return merged

    def _from_yfinance(self, yahoo_symbol: str) -> dict:
        try:
            import yfinance as yf
        except Exception:
            return {}

        self.limiter.wait()
        try:
            info = yf.Ticker(yahoo_symbol).info
        except Exception:
            return {}
        if not isinstance(info, dict):
            return {}
        return {
            "pe_ratio": _num(info.get("trailingPE")),
            "eps": _num(info.get("trailingEps")),
            "market_cap": _num(info.get("marketCap")),
            "dividend_yield": _num(info.get("dividendYield")),
            "pb_ratio": _num(info.get("priceToBook")),
            "ps_ratio": _num(info.get("priceToSalesTrailing12Months")),
            "roe": _num(info.get("returnOnEquity")),
            "roa": _num(info.get("returnOnAssets")),
            "debt_to_equity": _num(info.get("debtToEquity")),
            "current_ratio": _num(info.get("currentRatio")),
            "quick_ratio": _num(info.get("quickRatio")),
            "revenue_ttm": _num(info.get("totalRevenue")),
            "net_income_ttm": _num(info.get("netIncomeToCommon")),
            "free_cash_flow_ttm": _num(info.get("freeCashflow")),
            "raw": info,
        }

    def _from_tradingview(self, egx_symbol: str, tradingview_symbol: str | None) -> dict:
        try:
            from tradingview_screener import Query
        except Exception:
            return {}

        fields = [
            "name",
            "description",
            "market_cap_basic",
            "price_earnings_ttm",
            "earnings_per_share_basic_ttm",
            "dividend_yield_recent",
            "price_book_fq",
            "price_sales_current",
            "return_on_equity",
            "return_on_assets",
            "debt_to_equity",
            "current_ratio",
            "quick_ratio",
            "total_revenue_ttm",
            "net_income_ttm",
            "free_cash_flow_ttm",
        ]
        if self._tv_snapshot is None:
            try:
                _, self._tv_snapshot = (
                    Query().set_markets("egypt").select(*fields).limit(5000).get_scanner_data()
                )
            except Exception:
                return {}

        if self._tv_snapshot is None or self._tv_snapshot.empty:
            return {}

        # Start from an empty selection: only explicit matches below may fill it,
        # otherwise an unfiltered snapshot would leak row 0 into every ticker.
        matches = self._tv_snapshot.iloc[0:0]
        if tradingview_symbol:
            matches = self._tv_snapshot[self._tv_snapshot["name"] == tradingview_symbol]
        if matches.empty:
            matches = self._tv_snapshot[self._tv_snapshot["name"].astype(str).str.endswith(f":{egx_symbol}")]
        if matches.empty:
            matches = self._tv_snapshot[self._tv_snapshot["name"].astype(str) == egx_symbol]
        if matches.empty:
            return {}
        row = matches.iloc[0].to_dict()
        return {
            "pe_ratio": _num(row.get("price_earnings_ttm")),
            "eps": _num(row.get("earnings_per_share_basic_ttm")),
            "market_cap": _num(row.get("market_cap_basic")),
            "dividend_yield": _num(row.get("dividend_yield_recent")),
            "pb_ratio": _num(row.get("price_book_fq")),
            "ps_ratio": _num(row.get("price_sales_current")),
            "roe": _num(row.get("return_on_equity")),
            "roa": _num(row.get("return_on_assets")),
            "debt_to_equity": _num(row.get("debt_to_equity")),
            "current_ratio": _num(row.get("current_ratio")),
            "quick_ratio": _num(row.get("quick_ratio")),
            "revenue_ttm": _num(row.get("total_revenue_ttm")),
            "net_income_ttm": _num(row.get("net_income_ttm")),
            "free_cash_flow_ttm": _num(row.get("free_cash_flow_ttm")),
            "raw": row,
        }
