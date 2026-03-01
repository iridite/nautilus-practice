"""Delta management for arbitrage strategies."""

from decimal import Decimal


class DeltaManager:
    """
    Delta 管理器

    职责:
    - 计算现货和合约的名义价值
    - 验证 Delta 中性
    - 计算对冲比例
    """

    def calculate_notional(self, quantity: Decimal, price: float) -> Decimal:
        """
        计算名义价值: quantity * price

        Args:
            quantity: 持仓数量
            price: 价格

        Returns:
            名义价值

        Raises:
            ValueError: 价格为 0
        """
        if price == 0:
            raise ValueError("Price cannot be zero")

        return quantity * Decimal(str(price))

    def calculate_delta_ratio(self, spot_notional: Decimal, perp_notional: Decimal) -> float:
        """
        计算 Delta 比率: |spot - perp| / spot

        Args:
            spot_notional: 现货名义价值
            perp_notional: 合约名义价值

        Returns:
            Delta 比率

        Raises:
            ValueError: 现货名义价值为 0
        """
        if spot_notional == 0:
            raise ValueError("Spot notional cannot be zero")

        delta_diff = abs(spot_notional - perp_notional)
        return float(delta_diff / abs(spot_notional))

    def is_delta_neutral(
        self,
        spot_notional: Decimal,
        perp_notional: Decimal,
        tolerance: float = 0.005,
    ) -> bool:
        """
        判断是否 Delta 中性 (< tolerance)

        Args:
            spot_notional: 现货名义价值
            perp_notional: 合约名义价值
            tolerance: 容忍度，默认 0.005 (0.5%)

        Returns:
            是否 Delta 中性
        """
        if spot_notional == 0:
            return False

        delta_ratio = self.calculate_delta_ratio(spot_notional, perp_notional)
        return delta_ratio < tolerance

    def calculate_hedge_ratio(self, spot_price: float, perp_price: float) -> float:
        """
        计算对冲比例: spot_price / perp_price

        Args:
            spot_price: 现货价格
            perp_price: 合约价格

        Returns:
            对冲比例

        Raises:
            ValueError: 合约价格为 0
        """
        if perp_price == 0:
            raise ValueError("Perpetual price cannot be zero")

        return spot_price / perp_price
