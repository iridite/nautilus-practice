"""
CrewAI Tools - NautilusTrader Wrapper Bridge
桥接 CrewAI 与 NautilusTrader 回测引擎
"""
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from crewai_tools import tool


@tool("NautilusBacktest")
def run_nautilus_backtest(config_dict: str) -> str:
    """
    执行 NautilusTrader 回测

    Args:
        config_dict: JSON 格式的配置字典，包含:
            - symbol: 交易对 (如 "BTCUSDT")
            - start_date: 开始日期
            - end_date: 结束日期
            - strategy_params: 策略参数字典

    Returns:
        JSON 格式的回测结果，包含 Sharpe, Sortino, Max_Drawdown 等指标
    """
    try:
        config = json.loads(config_dict)
        base_dir = Path(__file__).resolve().parent.parent.parent

        # 构建回测命令
        cmd = [
            str(base_dir / ".venv/bin/python"),
            str(base_dir / "main.py"),
            "backtest",
            "--type", "high",
            "--skip-data"
        ]

        # 临时修改配置文件
        yaml_path = base_dir / "config/yaml/strategies/oi_divergence.yaml"
        original_content = yaml_path.read_text()

        try:
            # 注入参数
            import yaml
            with open(yaml_path, 'r') as f:
                yaml_config = yaml.safe_load(f)

            yaml_config['parameters'].update(config.get('strategy_params', {}))

            with open(yaml_path, 'w') as f:
                yaml.dump(yaml_config, f)

            # 执行回测
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=base_dir)

            # 解析结果
            output_dir = base_dir / "output"
            stats_file = list(output_dir.glob("*_stats.json"))

            if stats_file:
                with open(stats_file[0], 'r') as f:
                    stats = json.load(f)
                    return json.dumps({
                        "success": True,
                        "sharpe_ratio": stats.get("sharpe_ratio", 0),
                        "sortino_ratio": stats.get("sortino_ratio", 0),
                        "max_drawdown": stats.get("max_drawdown", 0),
                        "total_pnl": stats.get("total_pnl", 0),
                        "win_rate": stats.get("win_rate", 0),
                        "config": config
                    })
            else:
                return json.dumps({"success": False, "error": "No stats file generated", "stdout": result.stdout[-500:]})

        finally:
            # 恢复原始配置
            yaml_path.write_text(original_content)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool("MarketDataAnalyzer")
def analyze_market_conditions(symbol: str, start_date: str, end_date: str) -> str:
    """
    分析市场宏观环境

    Args:
        symbol: 交易对
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        市场状态报告 (JSON)
    """
    try:
        base_dir = Path(__file__).resolve().parent.parent.parent
        data_dir = base_dir / "data/csv" / symbol

        if not data_dir.exists():
            return json.dumps({"error": f"No data found for {symbol}"})

        # 简化分析：读取 OI 和 Funding 数据
        oi_files = list(data_dir.glob("*-oi-*.csv"))
        funding_files = list(data_dir.glob("*-funding-*.csv"))

        import pandas as pd

        analysis = {
            "symbol": symbol,
            "period": f"{start_date} to {end_date}",
            "oi_available": len(oi_files) > 0,
            "funding_available": len(funding_files) > 0,
            "market_state": "unknown"
        }

        if oi_files:
            df = pd.read_csv(oi_files[0])
            if 'open_interest' in df.columns:
                oi_volatility = df['open_interest'].pct_change().std()
                analysis["oi_volatility"] = float(oi_volatility)

                if oi_volatility > 0.1:
                    analysis["market_state"] = "high_volatility"
                elif oi_volatility < 0.03:
                    analysis["market_state"] = "low_liquidity"
                else:
                    analysis["market_state"] = "normal"

        return json.dumps(analysis)

    except Exception as e:
        return json.dumps({"error": str(e)})


@tool("AssetScreener")
def screen_assets_by_oi_potential(market_state: str, top_n: int = 5) -> str:
    """
    根据 OI 背离潜力筛选资产

    Args:
        market_state: 市场状态 (来自 MarketDataAnalyzer)
        top_n: 返回前 N 个推荐

    Returns:
        推荐交易品种列表 (JSON)
    """
    try:
        base_dir = Path(__file__).resolve().parent.parent.parent
        data_dir = base_dir / "data/csv"

        candidates = []

        for symbol_dir in data_dir.iterdir():
            if not symbol_dir.is_dir():
                continue

            oi_files = list(symbol_dir.glob("*-oi-*.csv"))
            if not oi_files:
                continue

            import pandas as pd
            df = pd.read_csv(oi_files[0])

            if 'open_interest' in df.columns and len(df) > 50:
                oi_std = df['open_interest'].std()
                oi_mean = df['open_interest'].mean()

                if oi_mean > 0:
                    cv = oi_std / oi_mean  # 变异系数
                    candidates.append({
                        "symbol": symbol_dir.name,
                        "oi_coefficient_variation": float(cv),
                        "oi_mean": float(oi_mean),
                        "data_points": len(df)
                    })

        # 排序：高波动 + 高持仓量
        candidates.sort(key=lambda x: x['oi_coefficient_variation'] * (x['oi_mean'] / 1e9), reverse=True)

        return json.dumps({
            "market_state": market_state,
            "top_recommendations": candidates[:top_n],
            "total_screened": len(candidates)
        })

    except Exception as e:
        return json.dumps({"error": str(e)})
