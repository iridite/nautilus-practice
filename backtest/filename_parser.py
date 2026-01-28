"""
文件名解析模块

提供健壮的文件名解析功能，支持多种命名格式。
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ParsedFilename:
    """解析后的文件名信息"""
    exchange: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str


class FilenameParser:
    """文件名解析器"""

    # 格式1: okx-BTCUSDT-1h-2020-01-01_2026-01-14.csv
    PATTERN_UNDERSCORE = re.compile(
        r'^(?P<exchange>\w+)-(?P<symbol>\w+)-(?P<timeframe>\w+)-'
        r'(?P<start_date>\d{4}-\d{2}-\d{2})_(?P<end_date>\d{4}-\d{2}-\d{2})\.csv$'
    )

    # 格式2: binance-DOGEUSDT-1h-2025-12-01-2025-12-30.csv
    PATTERN_DASH = re.compile(
        r'^(?P<exchange>\w+)-(?P<symbol>\w+)-(?P<timeframe>\w+)-'
        r'(?P<start_date>\d{4}-\d{2}-\d{2})-(?P<end_date>\d{4}-\d{2}-\d{2})\.csv$'
    )

    # 格式3: binance-DOGEUSDT-1h-2025-12-01.csv (单日期)
    PATTERN_SINGLE = re.compile(
        r'^(?P<exchange>\w+)-(?P<symbol>\w+)-(?P<timeframe>\w+)-'
        r'(?P<date>\d{4}-\d{2}-\d{2})\.csv$'
    )

    @classmethod
    def parse(cls, filename: str | Path) -> Optional[ParsedFilename]:
        """
        解析文件名

        Args:
            filename: 文件名或路径

        Returns:
            ParsedFilename: 解析结果，失败返回None
        """
        if isinstance(filename, Path):
            filename = filename.name

        # 尝试格式1
        match = cls.PATTERN_UNDERSCORE.match(filename)
        if match:
            return ParsedFilename(**match.groupdict())

        # 尝试格式2
        match = cls.PATTERN_DASH.match(filename)
        if match:
            return ParsedFilename(**match.groupdict())

        # 尝试格式3
        match = cls.PATTERN_SINGLE.match(filename)
        if match:
            d = match.groupdict()
            return ParsedFilename(
                exchange=d['exchange'],
                symbol=d['symbol'],
                timeframe=d['timeframe'],
                start_date=d['date'],
                end_date=d['date']
            )

        return None
