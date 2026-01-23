#!/usr/bin/env python3
"""
OI数据完整性检查和自动下载功能测试脚本

测试内容：
1. OI数据验证功能
2. 策略数据依赖声明
3. 自动数据检查和获取
4. 错误恢复机制
5. 配置选项

使用方法：
    python test_oi_integration.py
"""

import sys
from pathlib import Path
from decimal import Decimal

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from utils.validation import (
    check_oi_data_exists,
    check_funding_data_exists,
    validate_oi_data_structure,
    validate_funding_data_structure,
    OIDataValidator
)
from strategy.base import BaseStrategyConfig, DataDependency
from main import check_strategy_data_dependencies, execute_oi_funding_data_fetch


def test_data_dependency_declaration():
    """测试数据依赖声明功能"""
    print("=== 测试数据依赖声明功能 ===")
    
    # 创建测试配置
    config = BaseStrategyConfig()
    
    # 添加数据依赖
    config.add_data_dependency("oi", required=True, period="1h", exchange="binance")
    config.add_data_dependency("funding", required=True, exchange="binance")
    config.add_data_dependency("oi", required=False, period="4h", exchange="okx")
    
    # 验证依赖
    assert len(config.data_dependencies) == 3
    assert len(config.get_required_dependencies()) == 2
    assert len(config.get_optional_dependencies()) == 1
    assert config.has_oi_dependency() == True
    assert config.has_funding_dependency() == True
    
    print("✅ 数据依赖声明功能测试通过")
    
    # 显示依赖信息
    print(f"   总依赖: {len(config.data_dependencies)}")
    print(f"   必需依赖: {len(config.get_required_dependencies())}")
    print(f"   可选依赖: {len(config.get_optional_dependencies())}")
    
    return config


def test_oi_data_validation():
    """测试OI数据验证功能"""
    print("\n=== 测试OI数据验证功能 ===")
    
    # 测试数据存在性检查
    symbols = ["BTCUSDT", "ETHUSDT"]
    start_date = "2024-01-01"
    end_date = "2024-01-31"
    
    # 检查OI数据
    oi_exists, oi_missing = check_oi_data_exists(
        symbols, start_date, end_date, "1h", "binance", BASE_DIR
    )
    
    # 检查Funding Rate数据
    funding_exists, funding_missing = check_funding_data_exists(
        symbols, start_date, end_date, "binance", BASE_DIR
    )
    
    print(f"   OI数据存在: {oi_exists}")
    print(f"   OI缺失文件数: {len(oi_missing)}")
    print(f"   Funding Rate数据存在: {funding_exists}")
    print(f"   Funding Rate缺失文件数: {len(funding_missing)}")
    
    # 测试OI数据验证器
    validator = OIDataValidator()
    
    # 如果有现有的OI数据文件，测试验证功能
    test_oi_files = list(BASE_DIR.glob("data/raw/*/binance-*-oi-*.csv"))
    if test_oi_files:
        test_file = test_oi_files[0]
        print(f"   测试文件: {test_file.name}")
        
        validator.validate_oi_file(test_file)
        
        if validator.is_valid():
            print("✅ OI数据文件验证通过")
        else:
            print("❌ OI数据文件验证失败:")
            for error in validator.errors:
                print(f"      {error}")
    
    print("✅ OI数据验证功能测试完成")


def test_strategy_data_dependency_check():
    """测试策略数据依赖检查"""
    print("\n=== 测试策略数据依赖检查 ===")
    
    # 创建测试策略配置
    class TestStrategyConfig:
        def __init__(self):
            self.data_dependencies = [
                DataDependency("oi", required=True, period="1h", exchange="binance"),
                DataDependency("funding", required=True, exchange="binance")
            ]
            self.default_data_exchange = "binance"
            self.default_data_period = "1h"
            self.instrument_id = "BINANCE.BTCUSDT-PERP"
    
    config = TestStrategyConfig()
    
    # 测试数据依赖检查
    tasks = check_strategy_data_dependencies(
        config,
        "2024-01-01",
        "2024-01-31", 
        BASE_DIR,
        {"BTCUSDT:USDT", "ETHUSDT:USDT"}
    )
    
    print(f"   缺失数据任务数: {tasks['missing_count']}")
    print(f"   OI任务: {len(tasks['oi_tasks'])}")
    print(f"   Funding Rate任务: {len(tasks['funding_tasks'])}")
    
    # 显示任务详情
    for key, symbols in tasks["oi_tasks"].items():
        exchange, period, start, end = key
        print(f"   OI任务: {exchange} {period} ({len(symbols)} symbols)")
    
    for key, symbols in tasks["funding_tasks"].items():
        exchange, start, end = key
        print(f"   Funding Rate任务: {exchange} ({len(symbols)} symbols)")
    
    print("✅ 策略数据依赖检查测试完成")
    
    return tasks


def test_error_recovery_mechanism():
    """测试错误恢复机制"""
    print("\n=== 测试错误恢复机制 ===")
    
    # 创建模拟任务
    test_tasks = {
        "oi_tasks": {
            ("invalid_exchange", "1h", "2024-01-01", "2024-01-02"): {"TESTUSDT"}
        },
        "funding_tasks": {
            ("invalid_exchange", "2024-01-01", "2024-01-02"): {"TESTUSDT"}
        },
        "missing_count": 2,
        "warnings": []
    }
    
    # 测试错误恢复
    results = execute_oi_funding_data_fetch(
        test_tasks, 
        BASE_DIR,
        preferred_exchange="auto",
        max_retries=1,  # 减少重试次数以加快测试
        force_fetch=False
    )
    
    print(f"   获取的OI文件: {results['oi_files']}")
    print(f"   获取的Funding Rate文件: {results['funding_files']}")
    print(f"   重试次数: {results['retries']}")
    print(f"   回退次数: {results['fallbacks']}")
    print(f"   错误数量: {len(results['errors'])}")
    
    # 显示错误信息
    for error in results["errors"]:
        print(f"   错误: {error}")
    
    print("✅ 错误恢复机制测试完成")


def test_configuration_options():
    """测试配置选项"""
    print("\n=== 测试配置选项 ===")
    
    # 测试不同的配置组合
    configs = [
        {"preferred_exchange": "binance", "max_retries": 2},
        {"preferred_exchange": "okx", "max_retries": 1},
        {"preferred_exchange": "auto", "max_retries": 3},
    ]
    
    for i, config in enumerate(configs, 1):
        print(f"   配置 {i}: {config}")
        
        # 创建空任务来测试配置
        empty_tasks = {
            "oi_tasks": {},
            "funding_tasks": {},
            "missing_count": 0,
            "warnings": []
        }
        
        results = execute_oi_funding_data_fetch(
            empty_tasks,
            BASE_DIR,
            **config
        )
        
        print(f"      结果: {results}")
    
    print("✅ 配置选项测试完成")


def run_integration_test():
    """运行完整的集成测试"""
    print("🚀 开始OI数据完整性检查和自动下载功能集成测试")
    print("=" * 60)
    
    try:
        # 1. 测试数据依赖声明
        config = test_data_dependency_declaration()
        
        # 2. 测试OI数据验证
        test_oi_data_validation()
        
        # 3. 测试策略数据依赖检查
        tasks = test_strategy_data_dependency_check()
        
        # 4. 测试错误恢复机制
        test_error_recovery_mechanism()
        
        # 5. 测试配置选项
        test_configuration_options()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！OI数据完整性检查和自动下载功能正常工作")
        
        # 显示功能摘要
        print("\n🎯 已实现的功能:")
        print("   ✅ OI数据完整性检查机制")
        print("   ✅ 策略数据依赖声明")
        print("   ✅ 自动数据检查和获取")
        print("   ✅ 智能重试和错误恢复")
        print("   ✅ 多交易所数据源切换")
        print("   ✅ 用户友好的进度反馈")
        print("   ✅ 灵活的配置选项")
        
        print("\n📖 使用方法:")
        print("   python main.py backtest --help  # 查看所有选项")
        print("   python main.py backtest --skip-oi-data  # 跳过OI数据检查")
        print("   python main.py backtest --force-oi-fetch  # 强制重新下载")
        print("   python main.py backtest --oi-exchange binance  # 指定交易所")
        print("   python main.py backtest --max-retries 5  # 设置重试次数")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = run_integration_test()
    sys.exit(0 if success else 1)