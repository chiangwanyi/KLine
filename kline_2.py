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
# K线缓存（支持动态K线）
# =========================
class KlineBuffer:
    def __init__(self, maxlen=300):
        self.klines = deque(maxlen=maxlen)
        self.current = None
        self.lock = threading.Lock()

    def update(self, kline: dict, closed: bool):
        with self.lock:
            if closed:
                self.klines.append(kline)
                self.current = None
            else:
                self.current = kline

    def to_dataframe(self):
        with self.lock:
            data = list(self.klines)
            if self.current:
                data.append(self.current)
            return pd.DataFrame(data) if data else pd.DataFrame()


kline_buffer = KlineBuffer(MAX_KLINES)

# =========================
# Binance WebSocket
# =========================
class BinanceWSClient(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)

    def run(self):
        while True:
            try:
                self._connect()
            except Exception as e:
                print("WS 重连中：", e)
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
        ws.send(json.dumps({
            "method": "SUBSCRIBE",
            "params": [f"{SYMBOL}@kline_{INTERVAL}"],
            "id": 1
        }))

    def on_message(self, ws, message):
        data = json.loads(message)
        if "k" not in data:
            return

        k = data["k"]

        kline = {
            "time": datetime.fromtimestamp(k["t"] / 1000),
            "open": float(k["o"]),
            "high": float(k["h"]),
            "low": float(k["l"]),
            "close": float(k["c"]),
            "volume": float(k["v"])
        }

        kline_buffer.update(kline, closed=k["x"])

    def on_error(self, ws, error):
        print("WS 错误:", error)

    def on_close(self, ws, code, msg):
        print("WS 关闭:", code, msg)
        time.sleep(RECONNECT_DELAY)

# =========================
# Dash + TradingView 风格 Plotly
# =========================
app = dash.Dash(__name__)

app.layout = html.Div(
    style={"backgroundColor": "#0b0e11", "padding": "10px"},
    children=[
        html.H3(
            "BTCUSDT 永续合约 · 1分钟",
            style={"color": "white"}
        ),
        dcc.Graph(
            id="kline-chart",
            style={"height": "80vh"}
        ),
        dcc.Interval(id="interval", interval=1_000)
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
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350"
            )
        ]
    )

    fig.update_layout(
        xaxis=dict(
            type="date",
            rangeslider=dict(visible=False),
            showgrid=True,
            gridcolor="#1e222d"
        ),
        yaxis=dict(
            side="right",
            tickformat=".0f",
            showgrid=True,
            gridcolor="#1e222d"
        ),
        hovermode="x unified",
        spikedistance=-1,
        xaxis_showspikes=True,
        yaxis_showspikes=True,
        xaxis_spikemode="across",
        yaxis_spikemode="across",
        plot_bgcolor="#0b0e11",
        paper_bgcolor="#0b0e11",
        font=dict(color="white"),
        margin=dict(l=10, r=60, t=30, b=20)
    )

    return fig

# =========================
# 主入口
# =========================
if __name__ == "__main__":
    BinanceWSClient().start()
    app.run("127.0.0.1", 8050, debug=False)
