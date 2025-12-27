# server.py
from fastapi import FastAPI, Query # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import requests # type: ignore
from typing import Dict, Tuple

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BINANCE_FAPI = "https://fapi.binance.com/fapi/v1/klines"

# ============================
# 🔥 最近一次 K 线缓存
# ============================
KLINE_CACHE: Dict[str, Dict] = {
    "key": None,   # (symbol, interval, start, end)
    "data": None   # list[dict]
}


@app.get("/api/klines")
def get_klines(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("5m"),
    start: int = Query(..., description="unix 秒"),
    end: int = Query(..., description="unix 秒"),
):
    cache_key: Tuple = (symbol, interval, start, end)

    # ============================
    # 命中缓存
    # ============================
    if KLINE_CACHE["key"] == cache_key:
        print("✅ 命中 K 线缓存")
        return KLINE_CACHE["data"]

    print("🌐 请求 Binance K 线")

    resp = requests.get(
        BINANCE_FAPI,
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start,
            "endTime": end,
            "limit": 1000,
        },
        timeout=10
    )
    resp.raise_for_status()
    raw = resp.json()
    print(f"✅ 获取 {len(raw)} 条 K 线")
    data = [
        {
            "time": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in raw
    ]

    # 写入缓存
    KLINE_CACHE["key"] = cache_key
    KLINE_CACHE["data"] = data

    return data


if __name__ == "__main__":
    import uvicorn # type: ignore
    uvicorn.run("server:app", host="127.0.0.1", port=8001, reload=True)
