"""
CrewAI Tasks - 任务流编排
实现 Context-Aware 的有机连接逻辑
"""
from typing import List

from crewai import Task


def create_market_analysis_task(agent, symbol: str, start_date: str, end_date: str) -> Task:
    """任务1: 市场环境分析"""
    return Task(
        description=f"""分析 {symbol} 在 {start_date} 至 {end_date} 期间的市场环境。

        你需要：
        1. 使用 MarketDataAnalyzer 工具分析持仓量（OI）波动率
        2. 判断市场状态：高波动、低流动性、正常
        3. 输出结论：当前市场是否适合 OI 背离策略

        输出格式：
        {{
            "market_state": "high_volatility/low_liquidity/normal",
            "oi_volatility": 0.xx,
            "recommendation": "适合/不适合 OI 背离策略",
            "reason": "原因说明"
        }}
        """,
        agent=agent,
        expected_output="JSON 格式的市场状态报告"
    )


def create_asset_selection_task(agent, market_analysis_output: str) -> Task:
    """任务2: 资产筛选（依赖任务1的输出）"""
    return Task(
        description=f"""根据市场环境报告，筛选最适合的交易品种。

        市场环境报告：
        {market_analysis_output}

        你需要：
        1. 使用 AssetScreener 工具筛选 Top 5 币种
        2. 考虑 OI 深度、流动性、波动率
        3. 为每个推荐品种提供理由

        输出格式：
        {{
            "top_recommendations": [
                {{"symbol": "BTCUSDT", "score": 0.xx, "reason": "..."}},
                ...
            ]
        }}
        """,
        agent=agent,
        expected_output="JSON 格式的推荐品种列表",
        context=[]  # 将在运行时注入前置任务
    )


def create_strategy_design_task(agent, asset_selection_output: str) -> Task:
    """任务3: 策略逻辑设计（依赖任务2）"""
    return Task(
        description=f"""为选定的资产设计动态策略参数。

        推荐品种：
        {asset_selection_output}

        你需要：
        1. 根据资产的历史波幅，调整 Z-Score 窗口大小
        2. 设定 OI 下降阈值（建议范围：2%-5%）
        3. 设定资金费率过滤阈值（建议范围：15%-30%）
        4. 输出完整的策略参数配置

        输出格式：
        {{
            "symbol": "BTCUSDT",
            "strategy_params": {{
                "lookback_bars": 48,
                "oi_decline_threshold": 0.02,
                "funding_rate_threshold_annual": 15.0,
                "atr_period": 14,
                "atr_stop_multiplier": 2.0
            }},
            "rationale": "参数选择理由"
        }}
        """,
        agent=agent,
        expected_output="JSON 格式的策略参数配置",
        context=[]
    )


def create_backtest_optimization_task(agent, strategy_design_output: str, start_date: str, end_date: str) -> Task:
    """任务4: 回测与参数优化（依赖任务3）"""
    return Task(
        description=f"""执行 NautilusTrader 回测，测试多组参数组合。

        策略设计：
        {strategy_design_output}

        回测周期：{start_date} 至 {end_date}

        你需要：
        1. 使用 NautilusBacktest 工具执行回测
        2. 测试至少 3 组参数变体：
           - 基准参数（来自策略设计）
           - 保守参数（更大止损、更严格过滤）
           - 激进参数（更小止损、更宽松过滤）
        3. 记录每组参数的 Sharpe、Sortino、Max Drawdown
        4. 识别"参数平原"（稳定区域）

        输出格式：
        {{
            "backtest_results": [
                {{
                    "params": {{}},
                    "sharpe_ratio": 0.xx,
                    "sortino_ratio": 0.xx,
                    "max_drawdown": 0.xx,
                    "total_pnl": 0.xx
                }},
                ...
            ],
            "best_params": {{}},
            "parameter_sensitivity": "高/中/低"
        }}
        """,
        agent=agent,
        expected_output="JSON 格式的回测结果与参数敏感性分析",
        context=[]
    )


def create_risk_audit_task(agent, backtest_results_output: str) -> Task:
    """任务5: 风控审计（依赖任务4）"""
    return Task(
        description=f"""对回测结果进行严格审计，判断是否存在过拟合。

        回测结果：
        {backtest_results_output}

        你需要检查：
        1. 夏普比率是否过高（>3.0 需警惕）
        2. 最大回撤是否被低估（<5% 需警惕）
        3. 参数敏感性是否过高（微小变化导致结果剧变）
        4. 交易次数是否过少（<10 次不可靠）
        5. 胜率是否异常（>80% 或 <30% 需警惕）

        最终决策：
        - PASS: 策略可进入生产环境
        - FAIL: 存在过拟合风险，需重新优化
        - CONDITIONAL PASS: 可用，但需降低仓位或增加监控

        输出格式：
        {{
            "decision": "PASS/FAIL/CONDITIONAL_PASS",
            "risk_score": 0-100,
            "warnings": ["警告1", "警告2"],
            "recommendations": ["建议1", "建议2"]
        }}
        """,
        agent=agent,
        expected_output="JSON 格式的风控审计报告",
        context=[]
    )


def build_task_pipeline(agents: dict, symbol: str, start_date: str, end_date: str) -> List[Task]:
    """构建完整的任务流水线（带 Context 依赖）"""

    # 任务1: 市场分析
    task1 = create_market_analysis_task(
        agents['market_sentinel'],
        symbol,
        start_date,
        end_date
    )

    # 任务2: 资产筛选（依赖任务1）
    task2 = create_asset_selection_task(
        agents['asset_scout'],
        market_analysis_output="{{task1_output}}"
    )
    task2.context = [task1]

    # 任务3: 策略设计（依赖任务2）
    task3 = create_strategy_design_task(
        agents['strategy_architect'],
        asset_selection_output="{{task2_output}}"
    )
    task3.context = [task2]

    # 任务4: 回测优化（依赖任务3）
    task4 = create_backtest_optimization_task(
        agents['optimization_engineer'],
        strategy_design_output="{{task3_output}}",
        start_date=start_date,
        end_date=end_date
    )
    task4.context = [task3]

    # 任务5: 风控审计（依赖任务4）
    task5 = create_risk_audit_task(
        agents['risk_auditor'],
        backtest_results_output="{{task4_output}}"
    )
    task5.context = [task4]

    return [task1, task2, task3, task4, task5]
