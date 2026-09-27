from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ai_quant_trader.market_data.provider import (
    DemoMarketDataProvider,
    KisMarketDataProvider,
    MarketDataError,
    MarketDataProvider,
)

STATIC_DIR = Path(__file__).with_name("static")

app = FastAPI(
    title="AI Quant Trader Market Dashboard",
    description="Read-only KR/US market-cap dashboard",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@lru_cache(maxsize=1)
def provider() -> MarketDataProvider:
    if os.getenv("MARKET_DATA_DEMO", "false").lower() == "true":
        return DemoMarketDataProvider()
    app_key = os.getenv("KIS_APP_KEY", "")
    app_secret = os.getenv("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        raise MarketDataError("KIS_APP_KEY와 KIS_APP_SECRET을 서버 환경변수로 설정해 주세요.")
    return KisMarketDataProvider(
        app_key=app_key,
        app_secret=app_secret,
        base_url=os.getenv(
            "KIS_BASE_URL", "https://openapi.koreainvestment.com:9443"
        ),
    )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/market-cap")
async def market_cap(
    market: str = Query(pattern="^(KR|US)$"),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, object]:
    try:
        snapshot = await provider().top_market_cap(market, limit)  # type: ignore[arg-type]
    except (MarketDataError, httpx.HTTPError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
