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

# 初始化FastAPI应用实例
app = FastAPI()

# 币安期货K线数据API地址
BINANCE_API = "https://fapi.binance.com/fapi/v1/klines"
# 要查询的交易对：比特币兑泰达币（期货）
SYMBOL = "BTCUSDT"

# 时区映射字典：键为简洁标识，值为pytz对应的时区对象
TZ_MAP = {
    "UTC": pytz.utc,                  # 世界协调时间
    "NY": pytz.timezone("America/New_York"),  # 纽约时区
    "TOKYO": pytz.timezone("Asia/Tokyo"),     # 东京时区
    "SHANGHAI": pytz.timezone("Asia/Shanghai") # 上海时区
}

# 根路径路由：返回前端静态页面（GET请求）
@app.get("/", response_class=FileResponse)
def index():
    # 返回frontend目录下的index.html文件
    return FileResponse("frontend/index.html")

# 图表生成路由：接收查询参数，返回包含蜡烛图的HTML（GET请求）
@app.get("/chart", response_class=HTMLResponse)
def chart(
    # K线周期，默认1小时（可选值如1m, 15m, 4h, 1d等，符合币安API规范）
    interval: str = Query("1h"),
    # 开始时间，必填参数，格式示例：2025-12-25 00:00:00
    start: str = Query(...),
    # 结束时间，必填参数，格式同start
    end: str = Query(...),
    # 时区，默认纽约时区，可选值为TZ_MAP的键
    timezone: str = Query("NY"),
    # EMA长度，默认20，最小值1，最大值200
    ema_length: int = Query(20, ge=1, le=200)
):
    # 根据传入的时区标识获取对应的pytz时区对象
    tz = TZ_MAP[timezone]
    print(f'请求时间：{start} - {end}，时区：{timezone}，EMA长度：{ema_length}')
    # 1. 时间处理：将用户传入的本地时间字符串转为指定时区的datetime对象
    # 解析时间字符串为datetime（无时区），再绑定指定时区
    start_dt = tz.localize(datetime.strptime(start, "%Y-%m-%d %H:%M:%S"))
    end_dt = tz.localize(datetime.strptime(end, "%Y-%m-%d %H:%M:%S"))

    # 2. 转换为币安API要求的时间戳（UTC时区，毫秒级）
    # 先转为UTC时区，再转时间戳（秒），最后乘以1000转为毫秒
    start_ts = int(start_dt.astimezone(pytz.utc).timestamp() * 1000)
    end_ts = int(end_dt.astimezone(pytz.utc).timestamp() * 1000)

    # 3. 调用币安期货API获取K线数据
    resp = requests.get(BINANCE_API, params={
        "symbol": SYMBOL,       # 交易对
        "interval": interval,   # K线周期
        "startTime": start_ts,  # 开始时间戳（毫秒）
        "endTime": end_ts,      # 结束时间戳（毫秒）
        "limit": 1000           # 单次请求最大数据量（币安限制1500）
    })
    # 检查请求是否成功，失败则抛出异常
    resp.raise_for_status()

    # 4. 数据处理：将API返回的JSON数据转为DataFrame
    # 币安K线数据字段说明：
    # open_time: 开盘时间戳(ms), open: 开盘价, high: 最高价, low: 最低价, close: 收盘价
    # volume: 成交量, close_time: 收盘时间戳(ms), qav: 成交额, n: 成交笔数
    # tb: 主动买入成交量, tq: 主动买入成交额, i: 忽略字段
    json_data = resp.json()
    df = pd.DataFrame(json_data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","n","tb","tq","i"
    ])

    # 5. 时间格式转换：将开盘时间戳转为指定时区的datetime
    # 先转为UTC时区的datetime，再转换为用户指定的时区
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_convert(tz)
    # 6. 价格字段类型转换：将字符串转为浮点数（便于绘图计算）
    for c in ["open","high","low","close"]:
        df[c] = df[c].astype(float)

    # 7. 计算指定时段（00:00-04:00）的最高/最低价
    # 筛选出小时数在0到4之间的数据行
    session = df[(df["time"].dt.hour >= 0) & (df["time"].dt.hour < 4)]
    hi = session["high"].max()  # 该时段最高价
    lo = session["low"].min()   # 该时段最低价

    # 8. 计算EMA（指数移动平均线）
    # 使用pandas的ewm()函数计算指数加权移动平均
    # span参数设置为ema_length，adjust=False使用标准的EMA计算公式
    df[f'ema_{ema_length}'] = df['close'].ewm(span=ema_length, adjust=False).mean()

    # 9. 生成Plotly蜡烛图
    fig = go.Figure(go.Candlestick(
        x=df["time"],           # X轴：时间
        open=df["open"],        # 开盘价
        high=df["high"],        # 最高价
        low=df["low"],          # 最低价
        close=df["close"],      # 收盘价
        increasing_line_color="#26a69a",  # 上涨K线颜色（青绿色）
        decreasing_line_color="#ef5350"   # 下跌K线颜色（红色）
    ))

    # 10. 添加EMA指标线
    fig.add_trace(go.Scatter(
        x=df["time"],
        y=df[f'ema_{ema_length}'],
        mode='lines',
        name=f'EMA ({ema_length})',
        line=dict(color='blue', width=1.5),
        hovertemplate=f'EMA ({ema_length}): %{{y:.2f}}<extra></extra>'
    ))

    # 11. 添加时段高低价标记线
    # 添加红色虚线标记时段最高价，标注"时段最高价"
    fig.add_hline(y=hi, line=dict(color="red", dash="dash"), annotation_text="时段最高价")
    # 添加绿色虚线标记时段最低价，标注"时段最低价"
    fig.add_hline(y=lo, line=dict(color="green", dash="dash"), annotation_text="时段最低价")

    # 12. 图表样式配置
    fig.update_layout(
        xaxis_rangeslider_visible=False,  # 隐藏X轴下方的范围滑块
        yaxis_side="left",               # Y轴显示在右侧
        yaxis_tickformat=".0f",           # Y轴价格格式（无小数）
        hovermode="x unified",            # 悬停时统一显示X轴对应所有数据
        plot_bgcolor="#0b0e11",           # 绘图区域背景色（深灰）
        paper_bgcolor="#0b0e11",          # 整个图表背景色（深灰）
        font=dict(color="white"),         # 字体颜色（白色）
        height=700,                       # 图表高度
        # 新增中文标题和轴标签（可选优化）
        title={
            'text': f'{SYMBOL} K线图 ({interval}) - EMA({ema_length})',
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title="时间",
        yaxis_title="价格 (USDT)",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    # 13. 将图表转为HTML字符串返回（使用CDN加载PlotlyJS，减小体积）
    return fig.to_html(include_plotlyjs="cdn")

# 程序入口：启动FastAPI服务
if __name__ == "__main__":
    import uvicorn  # 导入ASGI服务器
    uvicorn.run(
        "server:app",    # 指定要运行的应用（模块名:实例名）
        host="127.0.0.1",# 绑定本地地址
        port=8001,       # 监听端口8001
        reload=True      # 开发模式：代码修改自动重启
    )