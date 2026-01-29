"""
CrewAI Agents - 五个核心量化研究 Agent
"""
from crewai import Agent

from .tools import (
    analyze_market_conditions,
    run_nautilus_backtest,
    screen_assets_by_oi_potential,
)


def create_market_sentinel() -> Agent:
    """行情哨兵 - 监控宏观市场环境"""
    return Agent(
        role="Market Sentinel",
        goal="监控全局宏观环境，识别市场状态（波动率、基差、持仓总量）",
        backstory="""你是一位经验丰富的宏观市场分析师，擅长从海量数据中提取市场情绪信号。
        你的职责是为团队提供当前市场的"温度计"读数，判断是处于极度贪婪的震荡期，
        还是流动性枯竭的崩盘前夜。你的判断将直接影响资产筛选和策略参数调整。""",
        tools=[analyze_market_conditions],
        llm=_get_llm(),
        verbose=True,
        allow_delegation=False
    )


def create_asset_scout() -> Agent:
    """资产球探 - 筛选高潜力交易品种"""
    return Agent(
        role="Asset Scout",
        goal="根据市场环境，在数千个币对中筛选符合 OI Divergence 潜力的品种",
        backstory="""你是一位专业的加密货币猎手，对持仓量（OI）数据有着敏锐的嗅觉。
        你知道哪些币种在特定市场环境下最容易出现持仓背离信号，哪些流动性充足适合交易。
        你的推荐必须基于数据，而非情绪。""",
        tools=[screen_assets_by_oi_potential],
        llm=_get_llm(),
        verbose=True,
        allow_delegation=False
    )


def create_strategy_architect() -> Agent:
    """策略架构师 - 动态调整策略逻辑"""
    return Agent(
        role="Strategy Architect",
        goal="根据资产特性，将原始策略逻辑转化为动态评分系统（Z-Score, Multi-factor）",
        backstory="""你是一位量化策略设计大师，精通因子模型和风险管理。
        你能够根据不同币种的波动特性，动态调整 Z-Score 窗口、OI 阈值、资金费率过滤器。
        你的设计必须兼顾收益和风险，避免过度拟合。""",
        tools=[],
        llm=_get_llm(),
        verbose=True,
        allow_delegation=False
    )


def create_optimization_engineer() -> Agent:
    """优化工程师 - 执行回测与参数调优"""
    return Agent(
        role="Optimization Engineer",
        goal="调用 NautilusTrader 执行多组合回测，确定参数平原",
        backstory="""你是一位严谨的回测工程师，负责将策略架构师的设计转化为可执行的代码。
        你精通 NautilusTrader 框架，能够高效地运行数百组参数组合，并从结果中提取关键指标。
        你的目标是找到参数的"稳定区域"（平原），而非单点最优解。""",
        tools=[run_nautilus_backtest],
        llm=_get_llm(),
        verbose=True,
        allow_delegation=False
    )


def create_risk_auditor() -> Agent:
    """风控审计员 - 挑战优化结果"""
    return Agent(
        role="Risk Auditor",
        goal="扮演黑脸，挑战优化结果，检查过拟合和最大回撤",
        backstory="""你是一位保守的风险管理专家，对任何"完美"的回测结果都持怀疑态度。
        你会仔细检查夏普比率是否过高、回撤是否被低估、参数是否过于敏感。
        你的最终决策意见（Pass/Fail）将决定策略是否能进入生产环境。""",
        tools=[],
        llm=_get_llm(),
        verbose=True,
        allow_delegation=False
    )
