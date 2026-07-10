from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from investor_egx.config import Settings
from investor_egx.http_utils import RateLimiter, build_retrying_session


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _score_to_label(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.5:
        return "STRONG_BUY"
    if score >= 0.1:
        return "BUY"
    if score > -0.1:
        return "NEUTRAL"
    if score > -0.5:
        return "SELL"
    return "STRONG_SELL"


@dataclass
class TechnicalsSentimentSource:
    settings: Settings
    _tv_snapshot: pd.DataFrame | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.limiter = RateLimiter(self.settings.min_request_interval_sec)
        self.session = build_retrying_session(
            user_agent=self.settings.user_agent,
            max_retries=self.settings.max_retries,
        )

    def fetch(
        self,
        egx_symbol: str,
        tradingview_symbol: str | None = None,
        exchange: str = "EGX",
        screener: str = "egypt",
        timeframe: str = "1D",
    ) -> dict:
        as_of_date = date.today().isoformat()
        ta_payload = self._from_tradingview_ta(egx_symbol, exchange=exchange, screener=screener, timeframe=timeframe)
        screener_payload = self._from_tradingview_screener(egx_symbol, tradingview_symbol)

        score = screener_payload.get("technical_score")
        technical_reco = ta_payload.get("technical_recommendation") or screener_payload.get("technical_recommendation")
        if technical_reco is None and score is not None:
            technical_reco = _score_to_label(score)

        analyst_reco = screener_payload.get("analyst_recommendation")
        if analyst_reco is None:
            analyst_reco = self._derive_analyst_label(
                screener_payload.get("analyst_buy"),
                screener_payload.get("analyst_hold"),
                screener_payload.get("analyst_sell"),
            )

        return {
            "as_of_date": as_of_date,
            "timeframe": timeframe,
            "technical_recommendation": technical_reco,
            "technical_score": score,
            "oscillators_recommendation": ta_payload.get("oscillators_recommendation")
            or screener_payload.get("oscillators_recommendation"),
            "moving_avg_recommendation": ta_payload.get("moving_avg_recommendation")
            or screener_payload.get("moving_avg_recommendation"),
            "buy_count": ta_payload.get("buy_count"),
            "neutral_count": ta_payload.get("neutral_count"),
            "sell_count": ta_payload.get("sell_count"),
            "analyst_recommendation": analyst_reco,
            "analyst_buy": screener_payload.get("analyst_buy"),
            "analyst_hold": screener_payload.get("analyst_hold"),
            "analyst_sell": screener_payload.get("analyst_sell"),
            "analyst_total": screener_payload.get("analyst_total"),
            "source": "tradingview_ta+tradingview_screener",
            "raw_json": {"tradingview_ta": ta_payload.get("raw"), "tradingview_screener": screener_payload.get("raw")},
        }

    def _from_tradingview_ta(
        self,
        symbol: str,
        exchange: str,
        screener: str,
        timeframe: str,
    ) -> dict:
        try:
            from tradingview_ta import Interval, TA_Handler
        except Exception:
            return {}

        interval_map = {
            "1m": "INTERVAL_1_MINUTE",
            "5m": "INTERVAL_5_MINUTES",
            "15m": "INTERVAL_15_MINUTES",
            "1h": "INTERVAL_1_HOUR",
            "4h": "INTERVAL_4_HOURS",
            "1D": "INTERVAL_1_DAY",
            "1W": "INTERVAL_1_WEEK",
            "1M": "INTERVAL_1_MONTH",
        }
        interval_name = interval_map.get(timeframe, "INTERVAL_1_DAY")
        interval = getattr(Interval, interval_name, Interval.INTERVAL_1_DAY)

        try:
            self.limiter.wait()
            analysis = TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=interval,
            ).get_analysis()
        except Exception:
            return {}

        summary = analysis.summary or {}
        oscillators = analysis.oscillators or {}
        moving_averages = analysis.moving_averages or {}
        return {
            "technical_recommendation": summary.get("RECOMMENDATION"),
            "buy_count": summary.get("BUY"),
            "neutral_count": summary.get("NEUTRAL"),
            "sell_count": summary.get("SELL"),
            "oscillators_recommendation": oscillators.get("RECOMMENDATION"),
            "moving_avg_recommendation": moving_averages.get("RECOMMENDATION"),
            "raw": {"summary": summary, "oscillators": oscillators, "moving_averages": moving_averages},
        }

    def _from_tradingview_screener(self, egx_symbol: str, tradingview_symbol: str | None) -> dict:
        try:
            from tradingview_screener import Query
        except Exception:
            return {}

        fields = [
            "name",
            "Recommend.All",
            "Recommend.MA",
            "Recommend.Other",
            "recommendation_mark",
            "recommendation_buy",
            "recommendation_hold",
            "recommendation_sell",
            "recommendation_total",
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
        score = _num(row.get("Recommend.All"))
        return {
            "technical_score": score,
            "technical_recommendation": _score_to_label(score),
            "moving_avg_recommendation": _score_to_label(_num(row.get("Recommend.MA"))),
            "oscillators_recommendation": _score_to_label(_num(row.get("Recommend.Other"))),
            "analyst_recommendation": self._mark_to_label(_num(row.get("recommendation_mark"))),
            "analyst_buy": int(row.get("recommendation_buy") or 0),
            "analyst_hold": int(row.get("recommendation_hold") or 0),
            "analyst_sell": int(row.get("recommendation_sell") or 0),
            "analyst_total": int(row.get("recommendation_total") or 0),
            "raw": row,
        }

    def scrape_analyst_signal_from_page(self, url: str) -> str | None:
        """
        Last-resort HTML scraping for pages that expose textual analyst labels.
        """
        try:
            import cloudscraper
        except Exception:
            return None
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            response = scraper.get(url, timeout=self.settings.request_timeout_sec)
            if response.status_code >= 400:
                return None
            html = response.text
        except Exception:
            return None
        for label in ("Strong Buy", "Buy", "Neutral", "Hold", "Sell", "Strong Sell"):
            if re.search(rf"\b{re.escape(label)}\b", html, flags=re.IGNORECASE):
                return label.upper().replace(" ", "_")
        return None

    def _derive_analyst_label(self, buy: int | None, hold: int | None, sell: int | None) -> str | None:
        if buy is None or hold is None or sell is None:
            return None
        counts = {"BUY": buy, "HOLD": hold, "SELL": sell}
        total = buy + hold + sell
        if total <= 0:
            return None
        top_label = max(counts, key=counts.get)
        top_share = counts[top_label] / total
        if top_label == "BUY" and top_share >= 0.7:
            return "STRONG_BUY"
        if top_label == "SELL" and top_share >= 0.7:
            return "STRONG_SELL"
        return top_label

    def _mark_to_label(self, mark: float | None) -> str | None:
        if mark is None:
            return None
        # TradingView's analyst recommendation mark is 1..5 with 1 = Strong Buy
        # (verified against recommendation_buy/hold/sell counts).
        if mark <= 1.5:
            return "STRONG_BUY"
        if mark <= 2.5:
            return "BUY"
        if mark <= 3.5:
            return "HOLD"
        if mark <= 4.5:
            return "SELL"
        return "STRONG_SELL"
