import json
import websocket
from datetime import datetime

# =========================
# WebSocket 回调
# =========================
def on_open(ws):
    print("WebSocket 已连接")

    sub_msg = {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@kline_1m"],
        "id": 1
    }
    ws.send(json.dumps(sub_msg))


def on_message(ws, message):
    data = json.loads(message)

    if "result" in data:
        return

    k = data["k"]

    if k["x"]:  # K线走完
        print({
            "time": datetime.fromtimestamp(k["t"] / 1000),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"])
        })


def on_error(ws, error):
    print("WebSocket 错误:", error)


def on_close(ws, close_status_code, close_msg):
    print("WebSocket 已关闭", close_status_code, close_msg)


# =========================
# 主程序（重点在这里）
# =========================
if __name__ == "__main__":
    websocket.enableTrace(False)

    ws = websocket.WebSocketApp(
        "wss://fstream.binance.com/ws",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    # 🔥 关键：代理设置
    ws.run_forever(
        http_proxy_host="127.0.0.1",
        http_proxy_port=7890,
        proxy_type="http"
    )
