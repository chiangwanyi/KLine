# server.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from typing import Dict, Tuple, List
from datetime import datetime
from zoneinfo import ZoneInfo
import threading
import json
import time
import websocket

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REST_API = "https://api.bitget.com/api/v2/mix/market/candles"

# ============================
# 🔥 K 线缓存
# ============================
KLINE_CACHE: Dict[str, Dict] = {
    "key": None,
    "data": []
}

# ============================
# WebSocket 状态
# ============================
WS_RUNNING = False
WS_SYMBOL = None
WS_INTERVAL = None


# ============================
# 工具函数
# ============================
def zoned_local_to_utc_ms(iso_local: str, timezone: str) -> int:
    dt = datetime.strptime(iso_local, "%Y-%m-%dT%H:%M")
    return int(dt.replace(tzinfo=ZoneInfo(timezone))
               .astimezone(ZoneInfo("UTC")).timestamp() * 1000)


def interval_to_ms(interval: str) -> int:
    unit = interval[-1]
    v = int(interval[:-1])
    return {"m": v * 60000, "h": v * 3600000, "d": v * 86400000}[unit]


def current_kline_open(interval_ms: int) -> int:
    now = int(time.time() * 1000)
    return now - (now % interval_ms)


# ============================
# WebSocket 处理
# ============================
def start_ws(symbol: str, interval: str):
    global WS_RUNNING, WS_SYMBOL, WS_INTERVAL

    if WS_RUNNING and WS_SYMBOL == symbol and WS_INTERVAL == interval:
        return

    WS_RUNNING = True
    WS_SYMBOL = symbol
    WS_INTERVAL = interval

    def on_message(ws, msg):
        data = json.loads(msg)
        k = data.get("data")
        if not k or not KLINE_CACHE["data"]:
            return

        t = int(k["ts"])
        last = KLINE_CACHE["data"][-1]

        candle = {
            "time": t,
            "open": float(k["open"]),
            "high": float(k["high"]),
            "low": float(k["low"]),
            "close": float(k["close"]),
            "volume": float(k["vol"]),
        }

        # 覆盖 or 追加
        if t == last["time"]:
            KLINE_CACHE["data"][-1] = candle
        elif t > last["time"]:
            KLINE_CACHE["data"].append(candle)

    def run():
        ws = websocket.WebSocketApp(
            "wss://ws.bitget.com/mix/v1/stream",
            on_message=on_message
        )
        ws.on_open = lambda ws: ws.send(json.dumps({
            "op": "subscribe",
            "args": [{
                "instType": "mc",
                "channel": f"candle{interval}",
                "instId": symbol
            }]
        }))
        ws.run_forever()

    threading.Thread(target=run, daemon=True).start()


# ============================
# REST API
# ============================
@app.get("/api/klines")
def get_klines(
    symbol: str = Query("BTCUSDT"),
    interval: str = Query("5m"),
    start: str = Query(...),
    end: str = Query(...),
    timezone: str = Query(...),
):
    cache_key: Tuple = (symbol, interval, start, end, timezone)

    if KLINE_CACHE["key"] == cache_key:
        return KLINE_CACHE["data"]

    start_ms = zoned_local_to_utc_ms(start, timezone)
    end_ms = zoned_local_to_utc_ms(end, timezone)
    interval_ms = interval_to_ms(interval)

    # ⭐ REST 只拉到当前K线开盘
    rest_end = min(end_ms, current_kline_open(interval_ms))

    all_klines: List[dict] = []
    fetch_start = start_ms

    while True:
        r = requests.get(
            REST_API,
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": fetch_start,
                "endTime": rest_end,
                "limit": 1000,
            },
            timeout=10
        )
        raw = r.json().get("data", [])
        if not raw:
            break

        for k in raw:
            t = int(k[0])
            if t >= rest_end:
                break
            all_klines.append({
                "time": t,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })

        next_start = int(raw[-1][0]) + interval_ms
        if next_start >= rest_end or len(raw) < 1000:
            break
        fetch_start = next_start

    # 写缓存
    KLINE_CACHE["key"] = cache_key
    KLINE_CACHE["data"] = all_klines

    # 🚀 启动 WebSocket 补偿今天
    start_ws(symbol, interval)

    return all_klines


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8001, reload=True)
