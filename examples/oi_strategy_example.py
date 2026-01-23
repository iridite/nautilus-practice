"""
OI Divergence 策略示例 - 演示数据依赖声明功能

这个示例展示了如何在策略中声明OI和Funding Rate数据依赖，
系统会自动检查和获取所需的数据。
"""

import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from strategy.base import BaseStrategy, BaseStrategyConfig, DataDependency


class OIDivergenceExampleConfig(BaseStrategyConfig):
    """
    OI Divergence 策略配置示例
    
    演示如何声明数据依赖
    """
    
    # 基础策略参数
    instrument_id: str = "BINANCE.BTCUSDT-PERP"
    trade_size: Optional[float] = 0.1
    stop_loss_pct: Optional[float] = 0.02
    
    # 策略特定参数
    lookback_bars: int = 48
    oi_threshold: float = 0.05
    funding_threshold: float = 0.0001
    
    # 数据依赖配置
    enable_auto_data_fetch: bool = True
    default_data_exchange: str = "binance"
    default_data_period: str = "1h"


def create_oi_strategy_config():
    """创建带有数据依赖的策略配置"""
    config = OIDivergenceExampleConfig()
    
    # 声明策略数据依赖
    config.add_data_dependency(
        data_type="oi",
        required=True,
        period="1h",
        exchange="binance",
        auto_fetch=True
    )
    
    config.add_data_dependency(
        data_type="funding",
        required=True,
        exchange="binance",
        auto_fetch=True
    )
    
    # 可选的备用数据源
    config.add_data_dependency(
        data_type="oi",
        required=False,
        period="4h",
        exchange="okx",
        auto_fetch=False  # 不自动获取，仅用于验证
    )
    
    return config


class OIDivergenceExampleStrategy(BaseStrategy):
    """
    OI Divergence 策略示例实现
    """
    
    def __init__(self, config: OIDivergenceExampleConfig):
        super().__init__(config)
        self.strategy_config = config
        
        # 策略状态
        self.oi_data = []
        self.funding_data = []
        
    def on_start(self):
        """策略启动"""
        super().on_start()
        
        # 显示数据需求摘要
        requirements = self.get_data_requirements()
        self.log.info(f"Strategy data requirements: {requirements}")
        
        # 检查是否有OI数据依赖
        if self.base_config.has_oi_dependency():
            self.log.info("Strategy requires OI data")
        
        # 检查是否有Funding Rate数据依赖
        if self.base_config.has_funding_dependency():
            self.log.info("Strategy requires Funding Rate data")
    
    def on_bar(self, bar):
        """处理Bar数据"""
        super().on_bar(bar)
        
        # 这里可以添加策略逻辑
        # 实际的OI数据会通过 on_data 方法接收
        pass
    
    def on_data(self, data):
        """处理自定义数据（OI、Funding Rate等）"""
        from utils.custom_data import OpenInterestData, FundingRateData
        
        if isinstance(data, OpenInterestData):
            self.oi_data.append(data)
            self.log.info(f"Received OI data: {data.open_interest}")
            
            # 保持数据长度
            if len(self.oi_data) > self.strategy_config.lookback_bars:
                self.oi_data.pop(0)
                
        elif isinstance(data, FundingRateData):
            self.funding_data.append(data)
            self.log.info(f"Received Funding Rate data: {data.funding_rate}")
            
            # 保持数据长度
            if len(self.funding_data) > 10:  # 保留最近10个资金费率
                self.funding_data.pop(0)
    
    def _check_oi_divergence(self) -> bool:
        """检查OI背离信号"""
        if len(self.oi_data) < self.strategy_config.lookback_bars:
            return False
        
        # 简单的OI背离检测逻辑
        recent_oi = [data.open_interest for data in self.oi_data[-10:]]
        if len(recent_oi) < 10:
            return False
        
        # 计算OI变化率
        oi_change = (recent_oi[-1] - recent_oi[0]) / recent_oi[0]
        return abs(oi_change) > self.strategy_config.oi_threshold
    
    def _check_funding_signal(self) -> bool:
        """检查资金费率信号"""
        if not self.funding_data:
            return False
        
        latest_funding = self.funding_data[-1].funding_rate
        return abs(latest_funding) > self.strategy_config.funding_threshold


# 使用示例
if __name__ == "__main__":
    # 创建策略配置
    config = create_oi_strategy_config()
    
    # 显示数据依赖信息
    print("=== 策略数据依赖信息 ===")
    print(f"总依赖数量: {len(config.data_dependencies)}")
    print(f"必需依赖: {len(config.get_required_dependencies())}")
    print(f"可选依赖: {len(config.get_optional_dependencies())}")
    print(f"需要OI数据: {config.has_oi_dependency()}")
    print(f"需要Funding Rate数据: {config.has_funding_dependency()}")
    
    print("\n=== 详细依赖列表 ===")
    for i, dep in enumerate(config.data_dependencies, 1):
        print(f"{i}. {dep}")
    
    # 创建策略实例
    strategy = OIDivergenceExampleStrategy(config)
    
    # 显示数据需求摘要
    requirements = strategy.get_data_requirements()
    print(f"\n=== 数据需求摘要 ===")
    for key, value in requirements.items():
        print(f"{key}: {value}")