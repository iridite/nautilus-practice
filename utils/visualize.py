import logging
from pathlib import Path
import warnings

# NautilusTrader Imports
from nautilus_trader.analysis import TearsheetConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.analysis.tearsheet import create_tearsheet


def generate_tearsheet_report(
    engine: BacktestEngine,
    output_path: str | Path = "../output/backtest_tearsheet.html",
    title: str = "Backtest Result",
    charts: list[str] = ["runinfo", "equity", "drawdown", "rolling_sharpe", "monthly_returns", "stats_table"],
) -> None:
    """
    仅生成 NautilusTrader 标准的可视化 HTML 报告 (Tearsheet)。
    
    参考文档: https://nautilustrader.io/docs/nightly/concepts/visualization

    Args:
        engine (BacktestEngine): 已运行完毕的回测引擎实例。
        output_path (str | Path): HTML 文件的保存完整路径。
        title (str): 报告中显示的标题。
    """
    
    if create_tearsheet is None:
        logging.error("❌ 无法导入 create_tearsheet 模块。请确保安装了依赖: pip install matplotlib quantstats")
        return

    # 路径处理
    path = Path(output_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # 强制确保扩展名为 .html
    if path.suffix != ".html":
        path = path.with_suffix(".html")

    config = TearsheetConfig(
        # theme="nautilus_dark",
        charts=charts,
        include_benchmark=True,
        show_logo=True,
    )

    # 屏蔽 Matplotlib/Quantstats 可能产生的无关警告
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
            
        # 调用核心函数
        # 注意：不同版本的参数名可能是 filename 或 output_path
        # 这里直接传入路径字符串，通常作为第二个位置参数或关键字参数 filename
        create_tearsheet(
            engine=engine,
            # title=title,
            # config=config,
            output_path=str(path), # 显式指定文件名
            # currency
        )

    print(f"✅ 报告已生成: {path.resolve()}")