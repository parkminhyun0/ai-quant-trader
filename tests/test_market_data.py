from decimal import Decimal

import httpx
import pytest

from ai_quant_trader.market_data.provider import DemoMarketDataProvider, KisMarketDataProvider


@pytest.mark.asyncio
async def test_demo_provider_returns_one_hundred_distinct_ranked_rows() -> None:
    snapshot = await DemoMarketDataProvider().top_market_cap("KR", 100)

    assert snapshot.mode == "demo"
    assert len(snapshot.stocks) == 100
    assert [stock.rank for stock in snapshot.stocks] == list(range(1, 101))
    assert len({stock.symbol for stock in snapshot.stocks}) == 100


@pytest.mark.asyncio
async def test_us_provider_merges_exchanges_and_sorts_by_market_cap() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        exchange = request.url.params["EXCD"]
        cap = {"NYS": "100", "NAS": "300", "AMS": "200"}[exchange]
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output2": [{
                    "rank": "1", "excd": exchange, "symb": exchange,
                    "ename": exchange, "last": "10", "diff": "1", "rate": "2.5",
                    "tomv": cap, "tvol": "1000",
                }],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KisMarketDataProvider(app_key="key", app_secret="secret", client=client)
        snapshot = await provider.top_market_cap("US", 3)

    assert [stock.symbol for stock in snapshot.stocks] == ["NAS", "AMS", "NYS"]
    assert snapshot.stocks[0].market_cap == Decimal(300)
