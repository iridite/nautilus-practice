"""
Dual Thrust Signal Generators

生成 Dual Thrust 策略的入场和出场信号。
"""


class DualThrustSignalGenerator:
    """
    Dual Thrust 信号生成器

    生成基于通道突破的交易信号。
    """

    def __init__(self):
        """初始化信号生成器"""
        pass

    def check_long_entry(self, price: float, upper_band: float | None) -> bool:
        """
        检查做多入场信号

        Args:
            price: 当前价格
            upper_band: 上轨

        Returns:
            True 表示应该做多
        """
        if upper_band is None:
            return False

        return price > upper_band

    def check_short_entry(self, price: float, lower_band: float | None) -> bool:
        """
        检查做空入场信号

        Args:
            price: 当前价格
            lower_band: 下轨

        Returns:
            True 表示应该做空
        """
        if lower_band is None:
            return False

        return price < lower_band

    def check_long_exit(self, price: float, lower_band: float | None) -> bool:
        """
        检查多头出场信号（反向突破止损）

        Args:
            price: 当前价格
            lower_band: 下轨

        Returns:
            True 表示应该平多
        """
        if lower_band is None:
            return False

        return price < lower_band

    def check_short_exit(self, price: float, upper_band: float | None) -> bool:
        """
        检查空头出场信号（反向突破止损）

        Args:
            price: 当前价格
            upper_band: 上轨

        Returns:
            True 表示应该平空
        """
        if upper_band is None:
            return False

        return price > upper_band
