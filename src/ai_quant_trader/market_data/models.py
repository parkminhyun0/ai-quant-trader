from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MarketStock(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1, le=100)
    market: Literal["KR", "US"]
    exchange: str
    symbol: str
    name: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    market_cap: Decimal
    volume: int = Field(ge=0)
    currency: Literal["KRW", "USD"]


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    market: Literal["KR", "US"]
    source: str
    mode: Literal["live", "demo"]
    as_of: datetime
    is_delayed: bool | None = None
    delay_note: str
    stocks: tuple[MarketStock, ...]
