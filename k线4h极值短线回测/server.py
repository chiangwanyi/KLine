# server.py
from fastapi import FastAPI, Query # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import requests # type: ignore
from typing import Dict, Tuple, List
from datetime import datetime
from zoneinfo import ZoneInfo

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
    "key": None,
    "data": None
}


# ============================
# ✅ 本地时间 + 时区 → UTC(ms)
# ============================
def zoned_local_to_utc_ms(iso_local: str, timezone: str) -> int:
    local_dt = datetime.strptime(iso_local, "%Y-%m-%dT%H:%M")
    zoned_dt = local_dt.replace(tzinfo=ZoneInfo(timezone))
    utc_dt = zoned_dt.astimezone(ZoneInfo("UTC"))
    return int(utc_dt.timestamp() * 1000)


# ============================
# ✅ interval → 毫秒
# ============================
def interval_to_ms(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])

    if unit == "m":
        return value * 60 * 1000
    if unit == "h":
        return value * 60 * 60 * 1000
    if unit == "d":
        return value * 24 * 60 * 60 * 1000

    raise ValueError(f"不支持的 interval: {interval}")


@app.get("/api/klines")
def get_klines(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("5m"),
    start: str = Query(..., description="YYYY-MM-DDTHH:mm"),
    end: str = Query(..., description="YYYY-MM-DDTHH:mm"),
    timezone: str = Query(..., description="IANA Timezone"),
):
    cache_key: Tuple = (symbol, interval, start, end, timezone)

    # ============================
    # 命中缓存
    # ============================
    if KLINE_CACHE["key"] == cache_key:
        print("✅ 命中 K 线缓存")
        return KLINE_CACHE["data"]

    print("🌐 请求 Binance K 线（自动分页）")

    try:
        start_utc_ms = zoned_local_to_utc_ms(start, timezone)
        end_utc_ms = zoned_local_to_utc_ms(end, timezone)

        if start_utc_ms >= end_utc_ms:
            raise ValueError("startTime >= endTime")

    except Exception as e:
        return {"error": f"时间解析失败: {e}"}

    interval_ms = interval_to_ms(interval)

    all_klines: List[dict] = []
    fetch_start = start_utc_ms

    while True:
        resp = requests.get(
            BINANCE_FAPI,
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": fetch_start,
                "endTime": end_utc_ms,
                "limit": 1000,
            },
            timeout=10
        )
        resp.raise_for_status()
        raw = resp.json()

        if not raw:
            break

        for k in raw:
            open_time = int(k[0])
            if open_time >= end_utc_ms:
                break

            all_klines.append({
                "time": open_time,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        # ⭐ 下一次请求的起点（关键）
        last_open_time = int(raw[-1][0])
        next_start = last_open_time + interval_ms

        if next_start >= end_utc_ms:
            break

        fetch_start = next_start

        # Binance 安全保护（可选）
        if len(raw) < 1000:
            break

    print(f"✅ 总共获取 {len(all_klines)} 条 K 线")

    # 写入缓存
    KLINE_CACHE["key"] = cache_key
    KLINE_CACHE["data"] = all_klines

    return all_klines


if __name__ == "__main__":
    import uvicorn # type: ignore
    uvicorn.run("server:app", host="127.0.0.1", port=8001, reload=True)
