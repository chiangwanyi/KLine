import json
import time
import threading
from collections import deque
from datetime import datetime

import websocket
import pandas as pd

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go

# =========================
# 配置
# =========================
WS_URL = "wss://fstream.binance.com/ws"
SYMBOL = "btcusdt"
INTERVAL = "1m"

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7890
PROXY_TYPE = "http"

MAX_KLINES = 300
RECONNECT_DELAY = 5

# =========================
# K线缓存
# =========================
class KlineBuffer:
    def __init__(self, maxlen=300):
        self.buffer = deque(maxlen=maxlen)
        self.lock = threading.Lock()

    def add(self, kline: dict):
        with self.lock:
            self.buffer.append(kline)

    def to_dataframe(self):
        with self.lock:
            if not self.buffer:
                return pd.DataFrame()
            return pd.DataFrame(list(self.buffer))


kline_buffer = KlineBuffer(MAX_KLINES)

# =========================
# Binance WebSocket 客户端
# =========================
class BinanceWSClient(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        while True:
            try:
                self._connect()
            except Exception as e:
                print("WS 异常，重连中：", e)
                time.sleep(RECONNECT_DELAY)

    def _connect(self):
        ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        ws.run_forever(
            http_proxy_host=PROXY_HOST,
            http_proxy_port=PROXY_PORT,
            proxy_type=PROXY_TYPE,
            ping_interval=20,
            ping_timeout=10
        )

    def on_open(self, ws):
        print("WebSocket 已连接")

        sub_msg = {
            "method": "SUBSCRIBE",
            "params": [f"{SYMBOL}@kline_{INTERVAL}"],
            "id": 1
        }
        ws.send(json.dumps(sub_msg))

    def on_message(self, ws, message):
        data = json.loads(message)
        if "k" not in data:
            return

        k = data["k"]

        # 只处理已完结K线
        if not k["x"]:
            return

        kline_buffer.add({
            "time": datetime.fromtimestamp(k["t"] / 1000),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"])
        })

    def on_error(self, ws, error):
        print("WebSocket 错误:", error)

    def on_close(self, ws, code, msg):
        print("WebSocket 关闭:", code, msg)
        time.sleep(RECONNECT_DELAY)

# =========================
# Dash + Plotly
# =========================
app = dash.Dash(__name__)

app.layout = html.Div(
    style={"width": "95%", "margin": "auto"},
    children=[
        html.H2("BTCUSDT 1分钟 永续合约（实时）"),
        dcc.Graph(id="kline-chart"),
        dcc.Interval(
            id="interval",
            interval=1_000,  # 1 秒刷新
            n_intervals=0
        )
    ]
)

@app.callback(
    Output("kline-chart", "figure"),
    Input("interval", "n_intervals")
)
def update_chart(_):
    df = kline_buffer.to_dataframe()

    if df.empty:
        return go.Figure()

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["time"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="BTCUSDT"
            )
        ]
    )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        margin=dict(l=20, r=20, t=30, b=20),
        height=600
    )

    return fig

# =========================
# 主入口
# =========================
if __name__ == "__main__":
    # 启动 WebSocket 后台线程
    ws_client = BinanceWSClient()
    ws_client.start()

    # 启动 Web 服务
    app.run(
        host="127.0.0.1",
        port=8050,
        debug=False
    )
