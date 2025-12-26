from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.loaders import CSVBarDataLoader
from nautilus_trader.persistence.wranglers import BarDataWrangler
# 引用方面总是或多或少的存在问题，尤其是 pyo3 相关的库，使用起来大概率会报错
from nautilus_trader.model import BarType

# 关于这个导入的路径，在教程中使用的是：nautilus_trader.test_kit.providers，但是实际上也是导入的这个路径。只不过 pylance 会报警告
import os
from pathlib import Path
from pandas import DataFrame

def loader(csv_path: Path, output_path: Path, instrument, bar_type: BarType)  -> tuple[ParquetDataCatalog, Path]:
    """
    Docstring for loader
    
    :param csv_path: Description
    :type csv_path: Path
    :param output_dir: Description
    :type output_dir: Path
    :param instrument: Description
    :param bar_type: Description
    :type bar_type: BarType
    :return: Description
    :rtype: [ParquetDataCatalog, catalog_path: Path]
    """  
    # TODO 检测该路径是否存在，若不存在便给出提示并进行自动重建文件夹
    if not os.path.exists(path=output_path):
        os.makedirs(name=output_path)
        print(f"Created output directory: {output_path}")
    
    print(f"Reading file: {csv_path}\nDesignated Output Path: {output_path}\nUsing Instrument: {instrument}")

    # Load the first CSV file into a pandas DataFrame
    df: DataFrame = CSVBarDataLoader.load(
        file_path=csv_path,
        index_col=0,
        usecols=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"], # pyright: ignore[reportArgumentType]
        date_format="%Y%m%d %H%M%S", 
    )

    
    df = df.sort_index()
    print(f"Loaded DataFrame preview:\n{df.head(n=2)}")

    wrangler = BarDataWrangler(
        bar_type,
        instrument
    )

    # catalog building
    catalog = ParquetDataCatalog(path=output_path)
    catalog.write_data([instrument]) # write the instrument metadata
    # worth noting that write_data can only accept a List when it is INSTRUMENT
    catalog.write_data(wrangler.process(df)) # Write the processed data to Parquet files

    bars = catalog.bars(bar_types=bar_type)
    print(f"Added {len(bars)} bars in catalog.")
    if bars:
        return catalog, output_path
    else:
        raise ValueError("There's no bar in the catalog.")

    
    

