from nautilus_trader.persistence.catalog import ParquetDataCatalog
import os
import pandas as pd

def loader(path_csv: str, output_dir: str, instrument):
    # TODO 检测该路径是否存在，若不存在便给出提示并进行自动重建文件夹
    print(f"Reading file: {path_csv}\nDesignated Output: {output_dir}\nUsing Instrument: {instrument}")

    catalog = ParquetDataCatalog(output_dir)
    catalog.write_instrument(instrument)

    df = pd.read_csv(path_csv)
    # 确保时间列是 datetime 类型，并设为 UTC
    df['datetime'] = pd.to_datetime(df['datetime'])
    if df['datetime'].dt.tz is None:
        df['datetime'] = df['datetime'].dt.tz_localize('UTC')
