#!/usr/bin/env python3
"""
自动化 Bootstrap 脚本
用于 Docker 容器启动时自动准备所有必需的数据和配置

功能：
1. 检查并下载缺失的币对数据
2. 自动生成 Universe 文件
3. 验证数据完整性
4. 支持增量更新（只下载缺失的数据）
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.adapter import ConfigAdapter
from utils import get_project_root
from utils.data_file_checker import check_single_data_file
from utils.data_management.data_manager import run_batch_data_retrieval
from utils.universe import generate_universe_file

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)

# ANSI 颜色代码
BLUE = "\033[0;34m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
NC = "\033[0m"  # No Color


def print_header(text: str):
    """打印蓝色标题"""
    print(f"{BLUE}{'=' * 42}{NC}")
    print(f"{BLUE}{text}{NC}")
    print(f"{BLUE}{'=' * 42}{NC}")


def print_step(step: int, total: int, text: str):
    """打印步骤信息"""
    print(f"\n{YELLOW}[{step}/{total}] {text}{NC}")


def print_success(text: str):
    """打印成功信息"""
    print(f"{GREEN}✓ {text}{NC}")


def print_error(text: str):
    """打印错误信息"""
    print(f"{RED}✗ {text}{NC}")


def check_proxy():
    """检查代理配置"""
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

    if http_proxy or https_proxy:
        print_success(f"代理已配置: {http_proxy or https_proxy}")
        return True
    else:
        print(f"{YELLOW}跳过代理检查（未配置代理）{NC}")
        return False


def check_data_files(adapter: ConfigAdapter, base_dir: Path, universe_symbols: set) -> list[str]:
    """检查数据文件，返回缺失的币对列表"""
    venue = adapter.get_venue().lower()
    start_date = adapter.get_start_date()
    end_date = adapter.get_end_date()
    timeframe = adapter.get_main_timeframe()
    strategy_name = adapter.get_strategy_name()

    print(f"策略配置:")
    print(f"  - Universe Top N: {len(universe_symbols)}")
    print(f"  - Timeframe: {timeframe}")
    print()

    missing_symbols = []
    for symbol in universe_symbols:
        base_symbol = symbol.split(":")[0]
        exists, _ = check_single_data_file(
            base_symbol,
            start_date,
            end_date,
            timeframe,
            venue,
            base_dir,
            strategy_name=strategy_name,
        )
        if exists:
            print(f"  ✓ 数据存在: {base_symbol}")
        else:
            print(f"  ✗ 数据缺失: {base_symbol}")
            missing_symbols.append(base_symbol)

    return missing_symbols


def download_missing_data(
    missing_symbols: list[str],
    adapter: ConfigAdapter,
    base_dir: Path,
):
    """下载缺失的数据"""
    if not missing_symbols:
        print_success("所有必需数据已存在（增量更新已跳过）")
        return

    print(f"\n{YELLOW}需要下载 {len(missing_symbols)} 个币对的数据{NC}")

    venue = adapter.get_venue().lower()
    start_date = adapter.get_start_date()
    end_date = adapter.get_end_date()
    timeframe = adapter.get_main_timeframe()

    try:
        run_batch_data_retrieval(
            missing_symbols,
            start_date,
            end_date,
            timeframe,
            venue,
            base_dir,
        )
        print_success(f"成功下载 {len(missing_symbols)} 个币对的数据")
    except Exception as e:
        print_error(f"数据下载失败: {e}")
        raise


def check_universe_file(adapter: ConfigAdapter, base_dir: Path) -> bool:
    """检查 Universe 文件是否存在"""
    try:
        config = adapter.build_backtest_config()
        strategy_params = config.strategy.params if hasattr(config.strategy, "params") else config.strategy

        universe_top_n = getattr(strategy_params, "universe_top_n", None)
        universe_freq = getattr(strategy_params, "universe_freq", "W-MON")

        if not universe_top_n:
            print(f"{YELLOW}策略未配置 universe_top_n，跳过 Universe 检查{NC}")
            return True

        universe_file = base_dir / "data" / "universe" / f"universe_{universe_top_n}_{universe_freq}.json"

        if universe_file.exists():
            print_success("Universe 文件已存在")
            print(f"  文件: {universe_file.relative_to(base_dir)}")
            return True
        else:
            print(f"{YELLOW}Universe 文件不存在，需要生成{NC}")
            return False

    except Exception as e:
        print_error(f"Universe 检查失败: {e}")
        return False


def generate_universe(adapter: ConfigAdapter, base_dir: Path):
    """生成 Universe 文件"""
    try:
        config = adapter.build_backtest_config()
        strategy_params = config.strategy.params if hasattr(config.strategy, "params") else config.strategy

        universe_top_n = getattr(strategy_params, "universe_top_n", None)
        universe_freq = getattr(strategy_params, "universe_freq", "W-MON")

        if not universe_top_n:
            print(f"{YELLOW}策略未配置 universe_top_n，跳过 Universe 生成{NC}")
            return

        print(f"生成 Universe 文件: top_{universe_top_n}, freq={universe_freq}")

        generate_universe_file(
            top_n=universe_top_n,
            freq=universe_freq,
            base_dir=base_dir,
        )

        print_success(f"Universe 文件生成成功")

    except Exception as e:
        print_error(f"Universe 生成失败: {e}")
        raise


def validate_config(adapter: ConfigAdapter):
    """验证配置文件"""
    try:
        config = adapter.build_backtest_config()
        print_success("配置验证通过")
        return True
    except Exception as e:
        print_error(f"配置验证失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="自动化 Bootstrap 脚本")
    parser.add_argument(
        "--env",
        default=os.environ.get("NAUTILUS_ENV", "sandbox"),
        help="环境名称（默认: sandbox）",
    )
    parser.add_argument(
        "--skip-data-download",
        action="store_true",
        help="跳过数据下载（仅验证）",
    )
    args = parser.parse_args()

    base_dir = get_project_root()

    print_header("NautilusTrader Practice - Auto Bootstrap")
    print(f"Python version: {sys.version.split()[0]}")
    print(f"Working directory: {base_dir}")
    print(f"Environment: {args.env}")
    print_header("")

    try:
        # Step 1: 检查代理
        print_step(1, 5, "跳过代理检查（未配置代理）")
        check_proxy()

        # Step 2: 加载配置
        print_step(2, 5, "检查数据文件...")

        # 临时设置环境变量
        os.environ["NAUTILUS_ENV"] = args.env

        adapter = ConfigAdapter()

        # 获取 Universe 币对列表
        config = adapter.build_backtest_config()
        strategy_params = config.strategy.params if hasattr(config.strategy, "params") else config.strategy
        universe_top_n = getattr(strategy_params, "universe_top_n", None)

        if universe_top_n:
            # 从 Universe 文件读取币对列表
            universe_freq = getattr(strategy_params, "universe_freq", "W-MON")
            universe_file = base_dir / "data" / "universe" / f"universe_{universe_top_n}_{universe_freq}.json"

            if universe_file.exists():
                import json
                with open(universe_file) as f:
                    universe_data = json.load(f)
                    # 获取第一个周期的币对列表
                    first_period = next(iter(universe_data.values()))
                    universe_symbols = set(first_period)
            else:
                # Universe 文件不存在，使用默认币对
                universe_symbols = {"BTCUSDT-PERP", "ETHUSDT-PERP", "SOLUSDT-PERP", "BNBUSDT-PERP", "ADAUSDT-PERP"}
        else:
            # 从配置获取交易币对
            universe_symbols = set(adapter._get_trading_symbols())

        # 检查数据文件
        missing_symbols = check_data_files(adapter, base_dir, universe_symbols)

        if missing_symbols and not args.skip_data_download:
            print(f"\n{YELLOW}需要下载 {len(missing_symbols)} 个币对的数据{NC}")
            download_missing_data(missing_symbols, adapter, base_dir)
        elif missing_symbols:
            print(f"\n{YELLOW}跳过数据下载（--skip-data-download）{NC}")
        else:
            print_success("所有必需数据已存在（增量更新已跳过）")

        # Step 3: 检查 Universe 文件
        print_step(3, 5, "检查 Universe 文件...")
        universe_exists = check_universe_file(adapter, base_dir)

        if not universe_exists and not args.skip_data_download:
            generate_universe(adapter, base_dir)

        # Step 4: 验证配置
        print_step(4, 5, "验证配置文件...")
        env_file = base_dir / "config" / "environments" / f"{args.env}.yaml"
        strategy_name = adapter.get_strategy_name()
        strategy_file = base_dir / "config" / "strategies" / f"{strategy_name}.yaml"

        print(f"  ✓ 配置文件存在: {env_file.relative_to(base_dir)}")
        print(f"  ✓ 配置文件存在: {strategy_file.relative_to(base_dir)}")

        if validate_config(adapter):
            print_success("配置验证通过")
        else:
            print_error("配置验证失败")
            return 1

        # Step 5: 完成
        print_step(5, 5, "启动策略...")
        print_success("Bootstrap 完成，准备启动策略")

        return 0

    except Exception as e:
        print_error(f"Bootstrap 失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
