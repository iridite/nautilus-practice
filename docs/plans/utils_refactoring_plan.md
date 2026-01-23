# Utils 重构架构计划

## 📊 分析结果

### 发现的重复函数
1. **`get_ms_timestamp()`**: 在 `utils.data_retrival` 和 `utils.oi_funding_fetcher` 中重复
2. **`retry_fetch()`**: 在 `utils.data_retrival` 和 `utils.oi_funding_fetcher` 中重复
3. **`resolve_symbol_and_type()`**: 符号解析逻辑
4. **`parse_timeframe()`**: 时间周期解析
5. **`check_data_exists()`**: 数据文件验证逻辑
6. **CSV 数据加载逻辑**: 在多个引擎中重复

## 🏗️ 新的 Utils 架构设计

```
utils/
├── __init__.py              # 统一导入接口
├── time_helpers.py          # 时间处理工具
├── network.py               # 网络请求和重试机制
├── validation.py            # 文件和数据验证
├── symbol_parser.py         # 交易所符号解析
├── data_loader.py           # 通用数据加载工具
├── config_helpers.py        # 配置解析助手
├── path_helpers.py          # 路径和文件操作
├── custom_data.py           # [保持不变] 自定义数据类型
├── instrument_loader.py     # [保持不变] 标的加载器
├── oi_funding_adapter.py    # [重构] OI/Funding 数据适配器
├── data_retrival.py         # [重构] 数据获取主模块
└── oi_funding_fetcher.py    # [重构] OI/Funding 数据获取
```

## 📝 各模块功能定义

### `time_helpers.py`
- `get_ms_timestamp(date_str: str) -> int`
- `get_ns_timestamp(date_str: str) -> int` 
- `format_timestamp(ts: int, format: str) -> str`
- `parse_datetime_range(start: str, end: str) -> tuple`

### `network.py`
- `retry_fetch(func, *args, **kwargs) -> Any`
- `RateLimit` 类用于 API 限流控制
- `NetworkError` 统一网络错误处理

### `validation.py`
- `check_file_exists(path: Path, min_size: int) -> tuple[bool, str|None]`
- `validate_csv_structure(path: Path, required_cols: list) -> bool`
- `detect_time_column(df: pd.DataFrame) -> str|None`

### `symbol_parser.py`
- `resolve_symbol_and_type(symbol: str) -> tuple[str, str]`
- `parse_timeframe(timeframe: str) -> tuple[BarAggregation, int]`
- `standardize_symbol(symbol: str, exchange: str) -> str`

### `data_loader.py`
- `load_csv_with_time_detection(path: Path, **kwargs) -> pd.DataFrame`
- `BatchDataLoader` 类用于批量数据加载
- `DataCache` 类用于数据缓存

### `config_helpers.py`
- `parse_universe_config(path: Path) -> dict`
- `extract_instrument_ids(config: dict, venue: str) -> set`
- `resolve_feed_parameters(feed_config: dict) -> dict`

## 🔄 重构流程

### Phase 1: 创建基础工具模块
1. 创建核心工具模块（time_helpers, network, validation）
2. 提取重复函数到对应模块
3. 添加类型注解和文档

### Phase 2: 重构现有模块
4. 重构 `utils.data_retrival` 使用新工具
5. 重构 `utils.oi_funding_fetcher` 使用新工具
6. 重构 `main.py` 使用新工具

### Phase 3: 系统整合
7. 创建统一的 `utils.__init__.py` 导入接口
8. 更新所有导入语句
9. 编写单元测试

### Phase 4: 验证和优化
10. 功能完整性验证
11. 性能优化
12. 文档更新

## 🎯 预期收益

1. **代码复用率提升**: 消除 5+ 个重复函数
2. **维护性提升**: 统一的工具函数便于维护和升级
3. **可测试性提升**: 模块化设计便于单元测试
4. **开发效率提升**: 统一接口减少学习成本
5. **错误处理统一**: 统一的异常处理和日志记录

## 🔍 重点关注事项

1. **向后兼容性**: 确保重构不破坏现有功能
2. **性能影响**: 避免增加不必要的性能开销
3. **类型安全**: 完善的类型注解和检查
4. **错误处理**: 统一且详细的错误信息
5. **文档完整性**: 清晰的使用示例和API文档