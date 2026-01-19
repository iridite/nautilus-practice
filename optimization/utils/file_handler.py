"""
文件读写工具
"""

import glob
import json
import os
from typing import Optional

from ..config import BACKTEST_RESULT_PATTERN, STRATEGY_FILE_PATH


def read_strategy_file() -> str:
    """读取策略文件"""
    try:
        with open(STRATEGY_FILE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "# No strategy code found"


def write_strategy_file(code: str) -> None:
    """写入策略文件"""
    with open(STRATEGY_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(code)


def get_latest_json_report(run_time: Optional[float] = None) -> dict:
    """获取最新的回测 JSON 报告"""
    files = glob.glob(BACKTEST_RESULT_PATTERN)

    if run_time is not None:
        files = [f for f in files if os.path.getmtime(f) > run_time]

    if not files:
        raise FileNotFoundError(
            f"未找到回测结果文件" + (f"（运行时间 > {run_time}）" if run_time else "")
        )

    latest_file = max(files, key=os.path.getmtime)
    print(f"📄 读取回测报告: {latest_file}")

    with open(latest_file, "r", encoding="utf-8") as f:
        return json.load(f)
