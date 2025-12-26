# 导入FastAPI核心模块和Query查询参数工具
from fastapi import FastAPI, Query
# 导入FastAPI的HTML响应和文件响应类
from fastapi.responses import HTMLResponse, FileResponse
# 导入请求库，用于调用币安API
import requests
# 导入pandas，用于数据处理
import pandas as pd
# 导入时区处理库
import pytz
# 导入时间处理模块
from datetime import datetime
# 导入plotly绘图库，用于生成蜡烛图
import plotly.graph_objs as go
# 导入JSON解析模块
import json
# 导入类型提示
from typing import Optional, Dict

# 初始化FastAPI应用实例
app = FastAPI()

# 币安期货K线数据API地址
BINANCE_API = "https://fapi.binance.com/fapi/v1/klines"
# 要查询的交易对：比特币兑泰达币（期货）
SYMBOL = "BTCUSDT"

# ============================
# 🔥 最近一次K线缓存
# ============================
KLINE_CACHE: Dict = {
    "key": None,   # (interval, timezone, start, end)
    "data": None   # {"df": DataFrame, "hi": float, "lo": float}
}

# 时区映射字典
TZ_MAP = {
    "UTC": pytz.utc,
    "NY": pytz.timezone("America/New_York"),
    "TOKYO": pytz.timezone("Asia/Tokyo"),
    "SHANGHAI": pytz.timezone("Asia/Shanghai")
}

# 主题配置
THEME_CONFIG = {
    "dark": {
        "plot_bgcolor": "#0b0e11",
        "paper_bgcolor": "#0b0e11",
        "font_color": "white",
        "increasing_color": "#26a69a",
        "decreasing_color": "#ef5350"
    },
    "light": {
        "plot_bgcolor": "#f8fafc",
        "paper_bgcolor": "#f8fafc",
        "font_color": "#1e293b",
        "increasing_color": "#26a69a",
        "decreasing_color": "#ef5350"
    }
}

@app.get("/", response_class=FileResponse)
def index():
    return FileResponse("frontend/index.html")


@app.get("/chart", response_class=HTMLResponse)
def chart(
    interval: str = Query("1h"),
    start: str = Query(...),
    end: str = Query(...),
    timezone: str = Query("NY"),
    emaConfig: Optional[str] = Query(None),
    isDarkMode: bool = Query(True)
):
    tz = TZ_MAP[timezone]

    # ============================
    # EMA配置解析（原样保留）
    # ============================
    ema_lines = []
    if emaConfig:
        try:
            ema_lines = json.loads(emaConfig)
            for ema in ema_lines:
                ema['length'] = int(ema.get('length', 20))
                ema['color'] = ema.get('color', '#0000ff')
                ema['opacity'] = float(ema.get('opacity', 1.0))
                ema['length'] = max(1, min(200, ema['length']))
                ema['opacity'] = max(0.1, min(1.0, ema['opacity']))
        except Exception:
            ema_lines = [{"length": 20, "color": "#0000ff", "opacity": 1.0}]
    else:
        ema_lines = [{"length": 20, "color": "#0000ff", "opacity": 1.0}]

    print(
        f'请求时间：{start} - {end}，时区：{timezone}，'
        f'EMA长度={[e["length"] for e in ema_lines]}，深色模式：{isDarkMode}'
    )

    # ============================
    # 时间处理（原样）
    # ============================
    start_dt = tz.localize(datetime.strptime(start, "%Y-%m-%d %H:%M:%S"))
    end_dt = tz.localize(datetime.strptime(end, "%Y-%m-%d %H:%M:%S"))

    start_ts = int(start_dt.astimezone(pytz.utc).timestamp() * 1000)
    end_ts = int(end_dt.astimezone(pytz.utc).timestamp() * 1000)

    # ============================
    # 🔥 缓存 Key
    # ============================
    cache_key = (interval, timezone, start, end)

    # ============================
    # 🔥 使用缓存 or 请求新数据
    # ============================
    if KLINE_CACHE["key"] == cache_key:
        print("✅ 命中K线缓存")
        df = KLINE_CACHE["data"]["df"].copy()
        hi = KLINE_CACHE["data"]["hi"]
        lo = KLINE_CACHE["data"]["lo"]

    else:
        print("🌐 请求Binance K线数据")

        resp = requests.get(BINANCE_API, params={
            "symbol": SYMBOL,
            "interval": interval,
            "startTime": start_ts,
            "endTime": end_ts,
            "limit": 1000
        })
        resp.raise_for_status()

        json_data = resp.json()
        df = pd.DataFrame(json_data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "n", "tb", "tq", "i"
        ])

        df["time"] = pd.to_datetime(
            df["open_time"], unit="ms", utc=True
        ).dt.tz_convert(tz)

        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)

        session = df[(df["time"].dt.hour >= 0) & (df["time"].dt.hour < 4)]
        hi = session["high"].max() if not session.empty else None
        lo = session["low"].min() if not session.empty else None

        # 写入缓存
        KLINE_CACHE["key"] = cache_key
        KLINE_CACHE["data"] = {
            "df": df.copy(),
            "hi": hi,
            "lo": lo
        }

    # ============================
    # EMA计算（原样）
    # ============================
    for ema in ema_lines:
        length = ema['length']
        df[f'ema_{length}'] = df['close'].ewm(
            span=length, adjust=False
        ).mean()

    # ============================
    # 以下 Plotly 图表代码：一行未改
    # ============================
    theme = THEME_CONFIG["dark"] if isDarkMode else THEME_CONFIG["light"]

    fig = go.Figure(go.Candlestick(
        x=df["time"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color=theme["increasing_color"],
        decreasing_line_color=theme["decreasing_color"]
    ))

    for ema in ema_lines:
        length = ema['length']
        fig.add_trace(go.Scatter(
            x=df["time"],
            y=df[f'ema_{length}'],
            mode='lines',
            name=f'EMA ({length})',
            line=dict(color=ema['color'], width=1.5),
            opacity=ema['opacity'],
            hovertemplate=f'EMA ({length}): %{{y:.2f}}<extra></extra>'
        ))

    if hi is not None:
        line_color = "#ef4444" if isDarkMode else "#991b1b"
        fig.add_hline(
            y=hi,
            line=dict(color=line_color, dash="dash"),
            annotation_text="时段最高价",
            annotation_font=dict(color=theme["font_color"])
        )

    if lo is not None:
        line_color = "#22c55e" if isDarkMode else "#065f46"
        fig.add_hline(
            y=lo,
            line=dict(color=line_color, dash="dash"),
            annotation_text="时段最低价",
            annotation_font=dict(color=theme["font_color"])
        )

    fig.update_layout(
        dragmode="pan",
        xaxis_rangeslider_visible=False,
        yaxis_side="right",
        yaxis_tickformat=".0f",
        hovermode="x unified",
        plot_bgcolor=theme["plot_bgcolor"],
        paper_bgcolor=theme["paper_bgcolor"],
        font=dict(color=theme["font_color"]),
        height=700,
        title={
            'text': f'{SYMBOL} K线图 ({interval})',
            'x': 0.5,
            'xanchor': 'center',
            'font': dict(size=16)
        },
        xaxis_title="时间",
        yaxis_title="价格 (USDT)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=12)
        ),
        xaxis=dict(
            gridcolor='rgba(255,255,255,0.1)' if isDarkMode else 'rgba(0,0,0,0.1)',
            linecolor=theme["font_color"],
            tickcolor=theme["font_color"]
        ),
        yaxis=dict(
            gridcolor='rgba(255,255,255,0.1)' if isDarkMode else 'rgba(0,0,0,0.1)',
            linecolor=theme["font_color"],
            tickcolor=theme["font_color"]
        )
    )

    fig.update_traces(
        hoverlabel=dict(
            bgcolor=theme["plot_bgcolor"],
            font_color=theme["font_color"],
            bordercolor=theme["font_color"]
        )
    )

    return fig.to_html(
        include_plotlyjs="cdn",
        config={
            "scrollZoom": True,
            "displaylogo": False
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8001,
        reload=True
    )
