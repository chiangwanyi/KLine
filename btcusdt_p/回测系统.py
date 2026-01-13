import requests
import pytz
from datetime import datetime, timedelta
import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import Optional
# 新增导入：用于提供静态文件服务和返回HTML响应
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# =========================
# 全局配置
# =========================
SYMBOL = "BTCUSDT"
INTERVAL = "5m"
SAVE_BASE_PATH = "./btcusdt_p/binance"
BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"
NY_TZ = pytz.timezone("Asia/Shanghai")
UTC_TZ = pytz.utc

app = FastAPI()

# 配置 CORS 中间件（核心修复部分）
origins = [
    "http://localhost:63343",  # 你的前端域名，必须指定具体值，不能用 *
    "http://localhost:8880",  # 新增：添加当前服务地址，避免前端访问跨域
    # 如果有其他环境（如生产环境），可以在这里添加，例如：
    # "https://your-production-domain.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许的源列表（关键：不能是 *）
    allow_credentials=True,  # 允许携带凭证（Cookie/认证信息），必须设为 True
    allow_methods=["*"],  # 允许所有请求方法（GET/POST/OPTIONS 等）
    allow_headers=["*"],  # 允许所有请求头
)

# 新增：挂载静态文件目录（当前目录）
# 这样可以访问同级目录下的所有静态文件（HTML/CSS/JS等）
app.mount("/static", StaticFiles(directory="."), name="static")


# =========================
# 新增：根路径路由，返回index.html内容
# =========================
@app.get("/", response_class=HTMLResponse, summary="返回首页index.html")
async def serve_index():
    """根路径返回同级目录下的index.html文件内容"""
    # 获取index.html的绝对路径
    html_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

    # 检查文件是否存在
    if not os.path.exists(html_file_path):
        raise HTTPException(status_code=404, detail="index.html文件不存在，请确保该文件在当前脚本的同级目录下")

    # 读取并返回HTML内容
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取index.html文件失败：{str(e)}")


# =========================
# 数据模型（参数校验）
# =========================
class DownloadKlineRequest(BaseModel):
    date: str  # 格式：YYYYMMDD 或 YYYY-MM-DD

    @field_validator("date")
    def validate_date_format(cls, v):
        """校验日期格式，并统一转为YYYYMMDD格式"""
        try:
            # 支持两种输入格式：YYYYMMDD 或 YYYY-MM-DD
            if "-" in v:
                dt = datetime.strptime(v, "%Y-%m-%d")
            else:
                dt = datetime.strptime(v, "%Y%m%d")
            return dt.strftime("%Y%m%d")
        except ValueError:
            raise ValueError("日期格式错误，请使用YYYYMMDD（如20250201）或YYYY-MM-DD（如2025-02-01）")


class GetKlineRequest(BaseModel):
    date: str  # 格式：YYYYMMDD 或 YYYY-MM-DD
    n: int  # 1~288（一天24小时，每5分钟一根，24*60/5=288）

    @field_validator("date")
    def validate_date_format(cls, v):
        try:
            if "-" in v:
                dt = datetime.strptime(v, "%Y-%m-%d")
            else:
                dt = datetime.strptime(v, "%Y%m%d")
            return dt.strftime("%Y%m%d")
        except ValueError:
            raise ValueError("日期格式错误，请使用YYYYMMDD（如20250201）或YYYY-MM-DD（如2025-02-01）")

    @field_validator("n")
    def validate_n_range(cls, v):
        if not (1 <= v <= 288):
            raise ValueError("n必须是1~288之间的整数（一天最多288根5分钟K线）")
        return v


# =========================
# 核心函数
# =========================
def get_kline_data(date_str: str) -> list:
    """
    根据日期获取对应日期的5分钟K线原始数据
    :param date_str: 日期字符串（YYYYMMDD）
    :return: 原始K线数据列表
    """
    # 构造日期的时间范围（当天00:00:00 到 23:59:59，上海时区）
    date_dt = datetime.strptime(date_str, "%Y%m%d")
    ny_start = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 00:00:00"
    ny_end = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} 23:59:59"

    # 时间转换（上海时区转UTC）
    ny_start_dt = NY_TZ.localize(datetime.strptime(ny_start, "%Y-%m-%d %H:%M:%S"))
    ny_end_dt = NY_TZ.localize(datetime.strptime(ny_end, "%Y-%m-%d %H:%M:%S"))
    utc_start_dt = ny_start_dt.astimezone(UTC_TZ)
    utc_end_dt = ny_end_dt.astimezone(UTC_TZ)

    start_ts = int(utc_start_dt.timestamp() * 1000)
    end_ts = int(utc_end_dt.timestamp() * 1000)

    # 请求Binance接口
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 1000  # 5分钟K线一天最多288根，1000足够
    }

    try:
        resp = requests.get(BINANCE_FUTURES_KLINES, params=params)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"获取K线数据失败：{str(e)}")


def save_kline_data(date_str: str, kline_data: list) -> str:
    """
    保存K线数据到本地指定路径
    :param date_str: 日期字符串（YYYYMMDD）
    :param kline_data: K线数据列表
    :return: 保存的文件路径
    """
    # 创建保存目录
    os.makedirs(SAVE_BASE_PATH, exist_ok=True)
    # 构造文件名
    file_name = f"{date_str}_5M.json"
    file_path = os.path.join(SAVE_BASE_PATH, file_name)

    # 写入文件
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(kline_data, f, ensure_ascii=False, indent=2)
        return file_path
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败：{str(e)}")


def read_kline_data(date_str: str) -> list:
    """
    从本地读取指定日期的K线数据
    :param date_str: 日期字符串（YYYYMMDD）
    :return: K线数据列表
    """
    file_name = f"{date_str}_5M.json"
    file_path = os.path.join(SAVE_BASE_PATH, file_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"未找到{date_str}的K线数据文件，请先调用下载接口")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败：{str(e)}")


# =========================
# Web接口
# =========================
@app.post("/download-kline", summary="加载指定日期的5分钟K线数据到本地")
def download_kline(request: DownloadKlineRequest):
    """
    下载指定日期的5分钟K线数据并保存到本地（路径：./btcusdt_p/binance/YYYYMMDD_5M.json）
    :param request: 包含date参数的请求体
    :return: 保存结果
    """
    date_str = request.date
    # 获取K线数据
    kline_data = get_kline_data(date_str)
    if not kline_data:
        raise HTTPException(status_code=404, detail=f"{date_str}未查询到K线数据")
    # 保存数据
    file_path = save_kline_data(date_str, kline_data)
    return {
        "code": 200,
        "message": "下载成功",
        "data": {
            "date": date_str,
            "file_path": file_path,
            "kline_count": len(kline_data)
        }
    }


@app.post("/get-kline", summary="获取指定日期的前n根5分钟K线数据")
def get_kline(request: GetKlineRequest):
    """
    获取指定日期的前n根5分钟K线数据（优先读取本地文件，本地无则先下载）
    :param request: 包含date和n参数的请求体
    :return: 前n根K线数据
    """
    date_str = request.date
    n = request.n

    # 先检查本地是否有文件，没有则先下载
    file_path = os.path.join(SAVE_BASE_PATH, f"{date_str}_5M.json")
    if not os.path.exists(file_path):
        kline_data = get_kline_data(date_str)
        if not kline_data:
            raise HTTPException(status_code=404, detail=f"{date_str}未查询到K线数据")
        save_kline_data(date_str, kline_data)
    else:
        kline_data = read_kline_data(date_str)

    # 返回前n根K线
    if len(kline_data) < n:
        raise HTTPException(status_code=400, detail=f"{date_str}仅查询到{len(kline_data)}根K线，不足{n}根")

    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "date": date_str,
            "n": n,
            "kline_data": kline_data[:n]  # 取前n根
        }
    }


# =========================
# 启动服务（本地测试用）
# =========================
if __name__ == "__main__":
    import uvicorn

    # 修复核心问题：模块名改为__main__（当前文件），而不是错误的"回测系统"
    # 同时绑定0.0.0.0，允许外部访问（包括前端页面）
    uvicorn.run(
        "__main__:app",
        host="0.0.0.0",  # 关键：绑定所有网卡，而非仅127.0.0.1
        port=8880,
        reload=True,
        log_level="info"  # 增加日志级别，便于排查问题
    )