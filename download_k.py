import requests
import pytz
from datetime import datetime
import json
import os

# =========================
# 配置
# =========================
SYMBOL = "BTCUSDT"
INTERVAL = "5m"
# 保存路径
SAVE_BASE_PATH = "./btcusdt_p/binance"

BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"

NY_TZ = pytz.timezone("Asia/Shanghai")
UTC_TZ = pytz.utc

# =========================
# 输入：时间日期范围
# =========================
NY_START = "2025-01-01 00:00:00"
NY_END   = "2025-01-01 23:59:59"

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
# 请求历史K线（仅保留原始数据）
# =========================
params = {
    "symbol": SYMBOL,
    "interval": INTERVAL,
    "startTime": start_ts,
    "endTime": end_ts,
    "limit": 1000
}

# 异常处理
try:
    resp = requests.get(BINANCE_FUTURES_KLINES, params=params)
    resp.raise_for_status()  # 抛出HTTP请求异常
    raw_klines = resp.json()  # 直接获取原始JSON数据，不做任何格式化
except requests.exceptions.RequestException as e:
    print(f"请求K线数据失败：{e}")
    raw_klines = []

# =========================
# 保存原始JSON文件
# =========================
# 1. 创建保存目录（如果不存在）
os.makedirs(SAVE_BASE_PATH, exist_ok=True)

# 2. 生成指定格式的文件名
date_str = ny_start_dt.strftime("%Y%m%d")
file_name = f"{date_str}_5M.json"
file_path = os.path.join(SAVE_BASE_PATH, file_name)

# 3. 写入原始JSON数据
try:
    with open(file_path, "w", encoding="utf-8") as f:
        # 仅保留原始数据，不做任何格式化（去掉indent也可以，保留是为了可读性）
        json.dump(raw_klines, f, ensure_ascii=False, indent=2)
    print(f"原始K线数据已成功保存到：{file_path}")
    print(f"共保存 {len(raw_klines)} 条5分钟K线数据")
except Exception as e:
    print(f"保存文件失败：{e}")