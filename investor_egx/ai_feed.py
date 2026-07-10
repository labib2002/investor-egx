from __future__ import annotations

import json
from typing import Any

import pandas as pd

from investor_egx.db import Database
from investor_egx.fees import ThndrFeeModel


def _pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return (new - old) / old * 100.0


def _to_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


def _daily_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    df = df.sort_values("trade_date").copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    last_close = _to_float(df["close"].iloc[-1])
    close_5 = _to_float(df["close"].iloc[-6]) if len(df) > 5 else None
    close_20 = _to_float(df["close"].iloc[-21]) if len(df) > 20 else None
    close_60 = _to_float(df["close"].iloc[-61]) if len(df) > 60 else None

    returns = df["close"].pct_change()
    vol_20 = returns.tail(20).std() * (252**0.5) * 100 if len(returns.dropna()) >= 20 else None

    return {
        "last_close": last_close,
        "ret_5d_pct": _pct_change(last_close, close_5),
        "ret_20d_pct": _pct_change(last_close, close_20),
        "ret_60d_pct": _pct_change(last_close, close_60),
        "avg_volume_20d": _to_float(df["volume"].tail(20).mean()),
        "realized_vol_20d_annualized_pct": _to_float(vol_20),
    }


def _intraday_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    df = df.sort_values("bar_ts_exchange").copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    last_close = _to_float(df["close"].iloc[-1])
    close_1h = _to_float(df["close"].iloc[-61]) if len(df) > 60 else None
    close_4h = _to_float(df["close"].iloc[-241]) if len(df) > 240 else None
    day_open = _to_float(df["open"].iloc[0]) if "open" in df else None

    return {
        "last_intraday_close": last_close,
        "ret_1h_pct": _pct_change(last_close, close_1h),
        "ret_4h_pct": _pct_change(last_close, close_4h),
        "session_move_pct": _pct_change(last_close, day_open),
        "intraday_volume_sum": _to_float(df["volume"].sum()),
    }


def build_ai_feed(
    db: Database,
    egx_symbol: str,
    intraday_rows: int = 360,
    daily_rows: int = 180,
    format_type: str = "json",
) -> str:
    profile = db.build_ai_profile(
        egx_symbol=egx_symbol,
        daily_lookback=daily_rows,
        intraday_lookback=intraday_rows,
    )
    daily_df = pd.DataFrame(profile["daily_prices_recent"])
    intraday_df = pd.DataFrame(profile["intraday_prices_recent"])
    fund = profile["fundamentals_latest"] or {}
    tech = (profile["technicals_recent"] or [{}])[0]

    fee_model = ThndrFeeModel()
    last_close = _to_float((daily_df["close"].iloc[0] if not daily_df.empty else None))
    example_notional = 10000.0
    if last_close and last_close > 0:
        shares = int(example_notional // last_close)
        example_notional = shares * last_close if shares > 0 else example_notional

    payload = {
        "ticker": profile["ticker"],
        "market_snapshot": {
            "daily": _daily_summary(daily_df),
            "intraday": _intraday_summary(intraday_df),
        },
        "fundamentals_latest": {
            "as_of_date": fund.get("as_of_date"),
            "pe_ratio": fund.get("pe_ratio"),
            "eps": fund.get("eps"),
            "market_cap": fund.get("market_cap"),
            "dividend_yield": fund.get("dividend_yield"),
            "pb_ratio": fund.get("pb_ratio"),
            "ps_ratio": fund.get("ps_ratio"),
            "roe": fund.get("roe"),
            "roa": fund.get("roa"),
            "debt_to_equity": fund.get("debt_to_equity"),
            "current_ratio": fund.get("current_ratio"),
            "quick_ratio": fund.get("quick_ratio"),
        },
        "technical_sentiment_latest": {
            "as_of_date": tech.get("as_of_date"),
            "timeframe": tech.get("timeframe"),
            "technical_recommendation": tech.get("technical_recommendation"),
            "technical_score": tech.get("technical_score"),
            "oscillators_recommendation": tech.get("oscillators_recommendation"),
            "moving_avg_recommendation": tech.get("moving_avg_recommendation"),
            "buy_count": tech.get("buy_count"),
            "neutral_count": tech.get("neutral_count"),
            "sell_count": tech.get("sell_count"),
            "analyst_recommendation": tech.get("analyst_recommendation"),
            "analyst_buy": tech.get("analyst_buy"),
            "analyst_hold": tech.get("analyst_hold"),
            "analyst_sell": tech.get("analyst_sell"),
            "analyst_total": tech.get("analyst_total"),
        },
        "thndr_fee_model": {
            "assumed_entry_notional_egp": round(example_notional, 2),
            "buy_fees_egp": round(fee_model.buy_fees(example_notional), 4),
            "sell_fees_egp": round(fee_model.sell_fees(example_notional), 4),
            "round_trip_fees_egp": round(fee_model.round_trip_fees(example_notional), 4),
            "break_even_move_pct": round(fee_model.break_even_move_pct(example_notional), 6),
        },
        "raw_tail": {
            "daily_prices_tail": profile["daily_prices_recent"][:10],
            "intraday_prices_tail": profile["intraday_prices_recent"][:30],
        },
    }

    if format_type.lower() == "markdown":
        return build_markdown_block(payload)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def build_markdown_block(payload: dict) -> str:
    ticker = payload["ticker"]
    daily = payload["market_snapshot"]["daily"]
    intraday = payload["market_snapshot"]["intraday"]
    fund = payload["fundamentals_latest"]
    tech = payload["technical_sentiment_latest"]
    fees = payload["thndr_fee_model"]
    lines = [
        f"## {ticker.get('egx_symbol')} ({ticker.get('company_name') or 'Unknown'})",
        "",
        "### Market Snapshot",
        f"- Last Close: {daily.get('last_close')}",
        f"- 5D/20D/60D Return (%): {daily.get('ret_5d_pct')} / {daily.get('ret_20d_pct')} / {daily.get('ret_60d_pct')}",
        f"- 20D Avg Volume: {daily.get('avg_volume_20d')}",
        f"- 20D Realized Vol (ann., %): {daily.get('realized_vol_20d_annualized_pct')}",
        f"- Intraday 1H/4H Return (%): {intraday.get('ret_1h_pct')} / {intraday.get('ret_4h_pct')}",
        "",
        "### Fundamentals",
        f"- P/E: {fund.get('pe_ratio')}, EPS: {fund.get('eps')}, MCap: {fund.get('market_cap')}",
        f"- Dividend Yield: {fund.get('dividend_yield')}, P/B: {fund.get('pb_ratio')}, P/S: {fund.get('ps_ratio')}",
        f"- ROE/ROA: {fund.get('roe')} / {fund.get('roa')}",
        "",
        "### Technical & Analyst Sentiment",
        f"- Technical: {tech.get('technical_recommendation')} (score={tech.get('technical_score')})",
        f"- Oscillators: {tech.get('oscillators_recommendation')} | MA: {tech.get('moving_avg_recommendation')}",
        f"- Analyst: {tech.get('analyst_recommendation')} (buy/hold/sell={tech.get('analyst_buy')}/{tech.get('analyst_hold')}/{tech.get('analyst_sell')})",
        "",
        "### THNDR Fees",
        f"- Entry Notional (EGP): {fees.get('assumed_entry_notional_egp')}",
        f"- Buy/Sell/Roundtrip Fees (EGP): {fees.get('buy_fees_egp')} / {fees.get('sell_fees_egp')} / {fees.get('round_trip_fees_egp')}",
        f"- Break-even Move (%): {fees.get('break_even_move_pct')}",
    ]
    return "\n".join(lines)
