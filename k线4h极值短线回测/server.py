from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import requests
import pandas as pd
import pytz
from datetime import datetime
import plotly.graph_objs as go

app = FastAPI()

BINANCE_API = "https://fapi.binance.com/fapi/v1/klines"
SYMBOL = "BTCUSDT"

TZ_MAP = {
    "UTC": pytz.utc,
    "NY": pytz.timezone("America/New_York"),
    "TOKYO": pytz.timezone("Asia/Tokyo"),
    "SHANGHAI": pytz.timezone("Asia/Shanghai"),
}

@app.get("/chart", response_class=HTMLResponse)
def chart(
    interval: str = Query("1h"),
    start: str = Query(...),   # 2025-12-25 00:00:00
    end: str = Query(...),
    timezone: str = Query("NY")
):
    tz = TZ_MAP[timezone]

    start_dt = tz.localize(datetime.strptime(start, "%Y-%m-%d %H:%M:%S"))
    end_dt = tz.localize(datetime.strptime(end, "%Y-%m-%d %H:%M:%S"))

    start_ts = int(start_dt.astimezone(pytz.utc).timestamp() * 1000)
    end_ts = int(end_dt.astimezone(pytz.utc).timestamp() * 1000)

    resp = requests.get(BINANCE_API, params={
        "symbol": SYMBOL,
        "interval": interval,
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 1000
    })
    resp.raise_for_status()

    df = pd.DataFrame(resp.json(), columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","n","tb","tq","i"
    ])

    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(tz)
    for c in ["open","high","low","close"]:
        df[c] = df[c].astype(float)

    # Session 00–04
    session = df[(df["time"].dt.hour >= 0) & (df["time"].dt.hour < 4)]
    hi = session["high"].max()
    lo = session["low"].min()

    fig = go.Figure(go.Candlestick(
        x=df["time"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350"
    ))

    fig.add_hline(y=hi, line=dict(color="red", dash="dash"), annotation_text="Session High")
    fig.add_hline(y=lo, line=dict(color="green", dash="dash"), annotation_text="Session Low")

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        yaxis_side="right",
        yaxis_tickformat=".0f",
        hovermode="x unified",
        plot_bgcolor="#0b0e11",
        paper_bgcolor="#0b0e11",
        font=dict(color="white"),
        height=700
    )

    return fig.to_html(include_plotlyjs="cdn")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
