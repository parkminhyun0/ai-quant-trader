from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

import httpx

from .models import MarketSnapshot, MarketStock

Market = Literal["KR", "US"]


class MarketDataError(RuntimeError):
    """Raised when the configured market data source cannot provide a snapshot."""


class MarketDataProvider(ABC):
    @abstractmethod
    async def top_market_cap(self, market: Market, limit: int = 100) -> MarketSnapshot:
        raise NotImplementedError


def _decimal(value: Any, *, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError) as error:
        raise MarketDataError(f"Invalid numeric value from provider: {value!r}") from error


def _integer(value: Any) -> int:
    try:
        return max(0, int(str(value or "0").replace(",", "")))
    except ValueError as error:
        raise MarketDataError(f"Invalid integer value from provider: {value!r}") from error


class KisMarketDataProvider(MarketDataProvider):
    """Korea Investment & Securities market-cap ranking adapter.

    Credentials stay on the server. This adapter does not submit orders.
    """

    DOMESTIC_PATH = "/uapi/domestic-stock/v1/ranking/market-cap"
    OVERSEAS_PATH = "/uapi/overseas-stock/v1/ranking/market-cap"
    TOKEN_PATH = "/oauth2/tokenP"
    DOMESTIC_TR_ID = "FHPST01740000"
    OVERSEAS_TR_ID = "HHDFS76350100"
    US_EXCHANGES = ("NYS", "NAS", "AMS")

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        base_url: str = "https://openapi.koreainvestment.com:9443",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError("KIS app key and secret are required")
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=UTC)
        self._token_lock = asyncio.Lock()

    async def _access_token(self) -> str:
        now = datetime.now(UTC)
        if self._token and now < self._token_expires_at:
            return self._token

        async with self._token_lock:
            now = datetime.now(UTC)
            if self._token and now < self._token_expires_at:
                return self._token

            response = await self._client.post(
                f"{self._base_url}{self.TOKEN_PATH}",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                },
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise MarketDataError("KIS token response did not include access_token")
            expires_in = int(payload.get("expires_in", 3600))
            self._token = str(token)
            self._token_expires_at = now + timedelta(seconds=max(60, expires_in - 60))
            return self._token

    async def _get(
        self,
        path: str,
        tr_id: str,
        params: dict[str, str],
        *,
        tr_cont: str = "",
    ) -> tuple[dict[str, Any], str]:
        token = await self._access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "content-type": "application/json; charset=utf-8",
        }
        if tr_cont:
            headers["tr_cont"] = tr_cont
        response = await self._client.get(
            f"{self._base_url}{path}",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("rt_cd", "0")) != "0":
            raise MarketDataError(
                f"KIS error {payload.get('msg_cd', 'UNKNOWN')}: "
                f"{payload.get('msg1', 'market data request failed')}"
            )
        return cast(dict[str, Any], payload), response.headers.get("tr_cont", "")

    async def top_market_cap(self, market: Market, limit: int = 100) -> MarketSnapshot:
        safe_limit = min(max(limit, 1), 100)
        if market == "KR":
            stocks = await self._domestic(safe_limit)
            note = "한국투자 Open API KRX 시가총액 순위 스냅샷"
        else:
            stocks = await self._us(safe_limit)
            note = "NYSE·NASDAQ·AMEX 순위를 합산 후 USD 시가총액으로 재정렬"
        return MarketSnapshot(
            market=market,
            source="Korea Investment & Securities Open API",
            mode="live",
            as_of=datetime.now(UTC),
            is_delayed=None,
            delay_note=f"{note}. 지연 여부는 계정의 시세 이용 조건을 따릅니다.",
            stocks=tuple(stocks),
        )

    async def _domestic(self, limit: int) -> list[MarketStock]:
        params = {
            "fid_input_price_2": "",
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20174",
            "fid_div_cls_code": "0",
            "fid_input_iscd": "0000",
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_input_price_1": "",
            "fid_vol_cnt": "",
        }
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        tr_cont = ""
        for _ in range(10):
            payload, next_tr_cont = await self._get(
                self.DOMESTIC_PATH,
                self.DOMESTIC_TR_ID,
                params,
                tr_cont=tr_cont,
            )
            for row in payload.get("output") or []:
                symbol = str(row.get("mksc_shrn_iscd", ""))
                if symbol and symbol not in seen:
                    rows.append(row)
                    seen.add(symbol)
            if len(rows) >= limit or next_tr_cont not in {"M", "F"}:
                break
            tr_cont = "N"
        normalized = [
            MarketStock(
                rank=index,
                market="KR",
                exchange="KRX",
                symbol=str(row.get("mksc_shrn_iscd", "")),
                name=str(row.get("hts_kor_isnm", "")),
                price=_decimal(row.get("stck_prpr")),
                change=_decimal(row.get("prdy_vrss")),
                change_percent=_decimal(row.get("prdy_ctrt")),
                market_cap=_decimal(row.get("stck_avls")),
                volume=_integer(row.get("acml_vol")),
                currency="KRW",
            )
            for index, row in enumerate(rows[:limit], start=1)
        ]
        return normalized

    async def _us(self, limit: int) -> list[MarketStock]:
        pages = await asyncio.gather(
            *(
                self._get(
                    self.OVERSEAS_PATH,
                    self.OVERSEAS_TR_ID,
                    {"EXCD": exchange, "VOL_RANG": "0", "KEYB": "", "AUTH": ""},
                )
                for exchange in self.US_EXCHANGES
            )
        )
        by_symbol: dict[str, dict[str, Any]] = {}
        for response, _ in pages:
            for row in response.get("output2") or []:
                symbol = str(row.get("symb", ""))
                if symbol:
                    by_symbol[symbol] = row
        ranked = sorted(by_symbol.values(), key=lambda row: _decimal(row.get("tomv")), reverse=True)
        return [
            MarketStock(
                rank=index,
                market="US",
                exchange=str(row.get("excd", "")),
                symbol=str(row.get("symb", "")),
                name=str(row.get("ename") or row.get("name") or row.get("symb", "")),
                price=_decimal(row.get("last")),
                change=_decimal(row.get("diff")),
                change_percent=_decimal(row.get("rate")),
                market_cap=_decimal(row.get("tomv")),
                volume=_integer(row.get("tvol")),
                currency="USD",
            )
            for index, row in enumerate(ranked[:limit], start=1)
        ]


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic UI fixture. Values are intentionally not real securities data."""

    async def top_market_cap(self, market: Market, limit: int = 100) -> MarketSnapshot:
        currency: Literal["KRW", "USD"] = "KRW" if market == "KR" else "USD"
        exchange = "KRX-DEMO" if market == "KR" else "US-DEMO"
        base_cap = Decimal(1000000000000) if market == "KR" else Decimal(1000000000)
        stocks = tuple(
            MarketStock(
                rank=rank,
                market=market,
                exchange=exchange,
                symbol=f"DEMO{rank:03d}",
                name=f"예시 종목 {rank:03d}",
                price=Decimal(100_000 - rank * 317 if market == "KR" else 500 - rank),
                change=Decimal((rank % 9) - 4),
                change_percent=Decimal((rank % 11) - 5) / Decimal(10),
                market_cap=base_cap * Decimal(101 - rank),
                volume=rank * 12_345,
                currency=currency,
            )
            for rank in range(1, min(max(limit, 1), 100) + 1)
        )
        return MarketSnapshot(
            market=market,
            source="UI verification fixture",
            mode="demo",
            as_of=datetime.now(UTC),
            is_delayed=None,
            delay_note="실제 종목이나 시세가 아닌 화면 검증용 데이터입니다.",
            stocks=stocks,
        )
