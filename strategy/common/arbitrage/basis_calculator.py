"""
Basis Calculator for Spot-Perpetual Arbitrage

This module provides functionality to calculate basis (price difference between
perpetual and spot markets) and determine trading signals for arbitrage strategies.
"""


class BasisCalculator:
    """
    基差计算器

    职责:
    - 计算现货和合约价格基差
    - 计算年化收益率
    - 判断开仓/平仓条件

    Examples:
        >>> calc = BasisCalculator()
        >>> basis = calc.calculate_basis(spot_price=100.0, perp_price=101.0)
        >>> annual_return = calc.calculate_annual_return(basis, holding_days=7)
        >>> should_open = calc.should_open_position(annual_return, threshold=15.0)
    """

    def calculate_basis(self, spot_price: float, perp_price: float) -> float:
        """
        计算基差: (perp_price - spot_price) / spot_price

        Args:
            spot_price: 现货价格
            perp_price: 永续合约价格

        Returns:
            基差（小数形式，如 0.01 表示 1%）

        Raises:
            ValueError: 如果价格为 0 或负数
        """
        if spot_price <= 0:
            raise ValueError(f"Spot price must be positive, got {spot_price}")
        if perp_price <= 0:
            raise ValueError(f"Perpetual price must be positive, got {perp_price}")

        basis = (perp_price - spot_price) / spot_price
        return basis

    def calculate_annual_return(self, basis: float, holding_days: int = 7) -> float:
        """
        计算年化收益率: basis * (365 / holding_days) * 3 * 100

        假设每天 3 次资金费率结算（每 8 小时一次）

        Args:
            basis: 基差（小数形式）
            holding_days: 持仓天数，默认 7 天

        Returns:
            年化收益率（百分比形式，如 15.0 表示 15%）

        Raises:
            ValueError: 如果 holding_days <= 0
        """
        if holding_days <= 0:
            raise ValueError(f"Holding days must be positive, got {holding_days}")

        # 年化收益率 = 基差 * (365天 / 持仓天数) * 每天3次结算 * 100转为百分比
        annual_return = basis * (365 / holding_days) * 3 * 100
        return annual_return

    def should_open_position(self, annual_return: float, threshold: float = 15.0) -> bool:
        """
        判断是否满足开仓条件

        Args:
            annual_return: 年化收益率（百分比）
            threshold: 开仓阈值（百分比），默认 15%

        Returns:
            True 如果年化收益率 > 阈值
        """
        return annual_return > threshold

    def should_close_position(self, annual_return: float, threshold: float = 5.0) -> bool:
        """
        判断是否满足平仓条件

        Args:
            annual_return: 年化收益率（百分比）
            threshold: 平仓阈值（百分比），默认 5%

        Returns:
            True 如果年化收益率 < 阈值
        """
        return annual_return < threshold
