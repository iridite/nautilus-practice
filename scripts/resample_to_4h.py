#!/usr/bin/env python3
"""
将 1h 数据重采样为 4h 数据
"""
import pandas as pd
from pathlib import Path


def resample_1h_to_4h(input_file: Path, output_file: Path):
    """将 1h OHLCV 数据重采样为 4h"""
    print(f"📖 Reading {input_file.name}...")
    df = pd.read_csv(input_file)

    # 转换时间戳
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('datetime', inplace=True)

    # 重采样为 4h
    print(f"🔄 Resampling to 4h...")
    df_4h = df.resample('4h').agg({
        'timestamp': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    })

    # 移除 NaN 行（如果有）
    df_4h = df_4h.dropna()

    # 重置索引并保留 datetime 列
    df_4h.reset_index(inplace=True)

    # 确保列顺序与原始文件一致
    df_4h = df_4h[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'datetime']]

    # 保存
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_4h.to_csv(output_file, index=False)
    print(f"✅ Saved {len(df_4h)} 4h bars to {output_file.name}")
    return len(df_4h)


def main():
    """主函数"""
    base_dir = Path(__file__).parent.parent / "data" / "raw"

    # 需要处理的币种
    symbols = ["BTCUSDT", "ETHUSDT"]

    for symbol in symbols:
        input_file = base_dir / symbol / f"binance-{symbol}-1h-2022-01-01_2026-01-01.csv"
        output_file = base_dir / symbol / f"binance-{symbol}-4h-2022-01-01_2026-01-01.csv"

        if not input_file.exists():
            print(f"⚠️  {input_file.name} not found, skipping...")
            continue

        if output_file.exists():
            print(f"⏭️  {output_file.name} already exists, skipping...")
            continue

        resample_1h_to_4h(input_file, output_file)

    print("\n✅ All done!")


if __name__ == "__main__":
    main()
