# server.py
from fastapi import FastAPI, Query # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import requests # type: ignore
from typing import Dict, Tuple
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
    "key": None,   # (symbol, interval, start, end, timezone)
    "data": None
}


# ============================
# ✅ 核心函数：本地时间 + 时区 → UTC 毫秒
# ============================
def zoned_local_to_utc_ms(iso_local: str, timezone: str) -> int:
    """
    iso_local: YYYY-MM-DDTHH:mm
    timezone: IANA 时区，如 America/New_York
    return: UTC 毫秒时间戳
    """
    # 1️⃣ 解析“纯本地时间”（不带时区）
    local_dt = datetime.strptime(iso_local, "%Y-%m-%dT%H:%M")

    # 2️⃣ 绑定指定时区（这是关键）
    zoned_dt = local_dt.replace(tzinfo=ZoneInfo(timezone))

    # 3️⃣ 转 UTC
    utc_dt = zoned_dt.astimezone(ZoneInfo("UTC"))

    # 4️⃣ 转毫秒时间戳
    return int(utc_dt.timestamp() * 1000)


@app.get("/api/klines")
def get_klines(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("5m"),

    # 🔴 前端现在传字符串，不是 int
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

    print("🌐 请求 Binance K 线")

    try:
        # ⭐ 核心转换：在后端统一完成
        start_utc_ms = zoned_local_to_utc_ms(start, timezone)
        end_utc_ms = zoned_local_to_utc_ms(end, timezone)

        if start_utc_ms >= end_utc_ms:
            raise ValueError("startTime >= endTime")

        print(
            f"⏱ 本地时间({timezone}): {start} ~ {end}\n"
            f"🌍 UTC(ms): {start_utc_ms} ~ {end_utc_ms}"
        )

    except Exception as e:
        return {"error": f"时间解析失败: {e}"}

    resp = requests.get(
        BINANCE_FAPI,
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start_utc_ms,
            "endTime": end_utc_ms,
            "limit": 1000,
        },
        timeout=10
    )
    resp.raise_for_status()
    raw = resp.json()

    print(f"✅ 获取 {len(raw)} 条 K 线")

    data = [
        {
            "time": int(k[0]),      # UTC 毫秒
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
