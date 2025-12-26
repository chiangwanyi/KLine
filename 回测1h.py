import requests
import pandas as pd
import pytz
from datetime import datetime, timedelta
import plotly.graph_objs as go

# =========================
# 配置
# =========================
SYMBOL = "BTCUSDT"
INTERVAL = "1h"

BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"

NY_TZ = pytz.timezone("America/New_York")
UTC_TZ = pytz.utc

# =========================
# 输入：纽约时间日期范围
# =========================
NY_START = "2025-12-25 00:00:00"
NY_END   = "2025-12-25 23:59:59"

# =========================
# 时间转换
# =========================
ny_start_dt = NY_TZ.localize(datetime.strptime(NY_START, "%Y-%m-%d %H:%M:%S"))
ny_end_dt   = NY_TZ.localize(datetime.strptime(NY_END, "%Y-%m-%d %H:%M:%S"))

utc_start_dt = ny_start_dt.astimezone(UTC_TZ)
utc_end_dt   = ny_end_dt.astimezone(UTC_TZ)

start_ts = int(utc_start_dt.timestamp() * 1000)
end_ts   = int(utc_end_dt.timestamp() * 1000)

# =========================
# 请求历史K线
# =========================
params = {
    "symbol": SYMBOL,
    "interval": INTERVAL,
    "startTime": start_ts,
    "endTime": end_ts,
    "limit": 24
}

resp = requests.get(BINANCE_FUTURES_KLINES, params=params)
resp.raise_for_status()

raw_klines = resp.json()

# =========================
# 转 DataFrame
# =========================
df = pd.DataFrame(raw_klines, columns=[
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "qav", "num_trades",
    "taker_base_vol", "taker_quote_vol", "ignore"
])

df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
df["time"] = df["time"].dt.tz_convert(NY_TZ)

for col in ["open", "high", "low", "close"]:
    df[col] = df[col].astype(float)

# =========================
# 计算 00:00–04:00 区间 High / Low
# =========================
session_df = df[
    (df["time"].dt.hour >= 0) &
    (df["time"].dt.hour < 4)
]

session_high = session_df["high"].max()
session_low = session_df["low"].min()

print("NY Session High (00–04):", session_high)
print("NY Session Low  (00–04):", session_low)

# =========================
# Plotly TradingView 风格绘图
# =========================
fig = go.Figure()

# 蜡烛图
fig.add_trace(go.Candlestick(
    x=df["time"],
    open=df["open"],
    high=df["high"],
    low=df["low"],
    close=df["close"],
    increasing_line_color="#26a69a",
    decreasing_line_color="#ef5350",
    name="BTCUSDT 1H"
))

# Session High 横线
fig.add_hline(
    y=session_high,
    line=dict(color="#ef5350", width=2, dash="dash"),
    annotation_text="NY 00–04 High",
    annotation_position="top right"
)

# Session Low 横线
fig.add_hline(
    y=session_low,
    line=dict(color="#26a69a", width=2, dash="dash"),
    annotation_text="NY 00–04 Low",
    annotation_position="bottom right"
)

# 布局（TradingView 风格）
fig.update_layout(
    title="BTCUSDT 永续 · 1小时（纽约时区）",
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
    plot_bgcolor="#0b0e11",
    paper_bgcolor="#0b0e11",
    font=dict(color="white"),
    margin=dict(l=20, r=60, t=40, b=20),
    height=700
)

fig.show()
