from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FreeApiAssessment:
    provider: str
    free_tier_summary: str
    egx_coverage: str
    intraday_on_free: str
    verdict: str


def build_assessment_matrix() -> list[FreeApiAssessment]:
    return [
        FreeApiAssessment(
            provider="Yahoo Finance (via yfinance)",
            free_tier_summary="No key, free unofficial endpoint access.",
            egx_coverage="Partial, symbol discovery via CAI listings is non-trivial and rate-limit sensitive.",
            intraday_on_free="Yes, but constrained windows and anti-bot throttling.",
            verdict="Great for fast prototyping, weak for guaranteed uptime.",
        ),
        FreeApiAssessment(
            provider="Investing.com (via investiny/cloudscraper)",
            free_tier_summary="No key for web endpoints, but scraping stability varies.",
            egx_coverage="Strong for EGX symbols and historical bars when endpoints remain unchanged.",
            intraday_on_free="Available through web chart endpoints; scraping reliability is the bottleneck.",
            verdict="Best no-cost fallback when engineered with retries and alternate routes.",
        ),
        FreeApiAssessment(
            provider="EODHD",
            free_tier_summary="Free package with daily call limits.",
            egx_coverage="Strong global exchange coverage including Egypt in paid tiers.",
            intraday_on_free="Limited by free-call quota and package restrictions.",
            verdict="Best EGX data quality among named APIs, but not truly unlimited free.",
        ),
        FreeApiAssessment(
            provider="Alpha Vantage",
            free_tier_summary="Strict request/day and request/minute caps on free key.",
            egx_coverage="Not clearly documented for EGX symbols end-to-end.",
            intraday_on_free="Limited by quota; practical coverage for EGX is uncertain.",
            verdict="Useful as secondary signal source, not primary EGX backbone.",
        ),
        FreeApiAssessment(
            provider="Marketstack",
            free_tier_summary="100 requests/month free plan.",
            egx_coverage="Global universe exists, but EGX quality/availability must be validated symbol-by-symbol.",
            intraday_on_free="No practical intraday for non-US in free plan.",
            verdict="Not suitable as core EGX intraday pipeline on free tier.",
        ),
        FreeApiAssessment(
            provider="Financial Modeling Prep",
            free_tier_summary="Free key intended for testing and bandwidth-limited usage.",
            egx_coverage="EGX availability is not clearly documented as a first-class free use case.",
            intraday_on_free="Constrained by plan limits and uncertain EGX depth.",
            verdict="Use only as optional enrich source after direct EGX feeds.",
        ),
    ]
