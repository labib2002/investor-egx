from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: str
    request_timeout_sec: int
    max_retries: int
    min_request_interval_sec: float
    user_agent: str
    alpha_vantage_api_key: str | None
    fmp_api_key: str | None
    marketstack_api_key: str | None
    eodhd_api_key: str | None

    @property
    def db_path_obj(self) -> Path:
        return Path(self.db_path).expanduser().resolve()


def load_settings() -> Settings:
    return Settings(
        db_path=os.getenv("INVESTOR_DB_PATH", "./data/investor_egx.sqlite3"),
        request_timeout_sec=int(os.getenv("INVESTOR_REQUEST_TIMEOUT_SEC", "30")),
        max_retries=int(os.getenv("INVESTOR_MAX_RETRIES", "4")),
        min_request_interval_sec=float(os.getenv("INVESTOR_MIN_REQUEST_INTERVAL_SEC", "0.45")),
        user_agent=os.getenv(
            "INVESTOR_USER_AGENT",
            "InvestorEGXBot/1.0 (+https://github.com/your-org/investor-egx-pipeline)",
        ),
        alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY"),
        fmp_api_key=os.getenv("FMP_API_KEY"),
        marketstack_api_key=os.getenv("MARKETSTACK_API_KEY"),
        eodhd_api_key=os.getenv("EODHD_API_KEY"),
    )
