"""
CrewAI 量化策略流水线 - 主入口
"""
import json
from pathlib import Path

from crewai import Crew, Process

from .agents import (
    create_asset_scout,
    create_market_sentinel,
    create_optimization_engineer,
    create_risk_auditor,
    create_strategy_architect,
)
from .tasks import build_task_pipeline


def run_strategy_research_pipeline(
    symbol: str = "BTCUSDT",
    start_date: str = "2024-01-01",
    end_date: str = "2024-12-31",
    output_dir: str = None
):
    """
    运行完整的策略研究流水线

    Args:
        symbol: 主要分析的交易对
        start_date: 回测开始日期
        end_date: 回测结束日期
        output_dir: 输出目录（默认为 optimization/crew_ai/output）
    """

    print("=" * 70)
    print("🚀 CrewAI 量化策略自动化研究系统")
    print("=" * 70)
    print(f"目标品种: {symbol}")
    print(f"回测周期: {start_date} ~ {end_date}")
    print("=" * 70)

    # 创建五个核心 Agent
    agents = {
        'market_sentinel': create_market_sentinel(),
        'asset_scout': create_asset_scout(),
        'strategy_architect': create_strategy_architect(),
        'optimization_engineer': create_optimization_engineer(),
        'risk_auditor': create_risk_auditor()
    }

    print("\n✅ 已创建 5 个核心 Agent:")
    for name, agent in agents.items():
        print(f"   - {agent.role}")

    # 构建任务流水线
    tasks = build_task_pipeline(agents, symbol, start_date, end_date)

    print(f"\n✅ 已构建 {len(tasks)} 个任务流:")
    for i, task in enumerate(tasks, 1):
        print(f"   {i}. {task.description.split('.')[0][:50]}...")

    # 创建 Crew（使用顺序执行确保 Context 传递）
    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,  # 顺序执行，确保依赖关系
        verbose=2  # 详细日志
    )

    print("\n" + "=" * 70)
    print("🔥 开始执行流水线...")
    print("=" * 70 + "\n")

    # 执行流水线
    try:
        result = crew.kickoff()

        print("\n" + "=" * 70)
        print("✅ 流水线执行完成")
        print("=" * 70)

        # 保存结果
        if output_dir is None:
            output_dir = Path(__file__).parent / "output"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"research_result_{symbol}_{start_date}_{end_date}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "symbol": symbol,
                "period": f"{start_date} ~ {end_date}",
                "result": str(result),
                "tasks_completed": len(tasks)
            }, f, indent=2, ensure_ascii=False)

        print(f"\n📊 结果已保存至: {output_file}")

        # 打印最终报告
        print("\n" + "=" * 70)
        print("📋 最终研究报告")
        print("=" * 70)
        print(result)
        print("=" * 70)

        return result

    except Exception as e:
        print(f"\n❌ 流水线执行失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="CrewAI 量化策略自动化研究系统")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对")
    parser.add_argument("--start-date", default="2024-01-01", help="开始日期")
    parser.add_argument("--end-date", default="2024-12-31", help="结束日期")
    parser.add_argument("--output-dir", default=None, help="输出目录")

    args = parser.parse_args()

    run_strategy_research_pipeline(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
