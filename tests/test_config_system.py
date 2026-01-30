#!/usr/bin/env python3
"""
配置系统测试脚本

测试新配置系统的各项功能，确保与现有系统的兼容性。
"""

import sys
import traceback
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_config_loading():
    """测试配置加载功能"""
    print("🧪 Testing configuration loading...")
    
    try:
        from core.loader import ConfigLoader, load_config
        
        # 测试配置加载器
        loader = ConfigLoader()
        
        # 测试环境配置加载
        print("  📁 Testing environment config loading...")
        env_config = loader.load_environment_config('dev')
        print(f"    ✅ Dev environment loaded: {env_config.trading.venue}")
        
        # 测试策略配置加载
        print("  📁 Testing strategy config loading...")
        strategy_config = loader.load_strategy_config('rs_squeeze')
        print(f"    ✅ RS Squeeze strategy loaded: {strategy_config.name}")
        
        # 测试活跃配置加载
        print("  📁 Testing active config loading...")
        active_config = loader.load_active_config()
        print(f"    ✅ Active config loaded: {active_config.environment}/{active_config.strategy}")
        
        # 测试便利函数
        print("  📁 Testing convenience function...")
        env_cfg, strategy_cfg, active_cfg = load_config()
        print(f"    ✅ Load config function works: {env_cfg.trading.venue}")
        
        return True
        
    except Exception as e:
        print(f"    ❌ Config loading failed: {e}")
        traceback.print_exc()
        return False


def test_config_manager():
    """测试配置管理器功能"""
    print("🧪 Testing configuration manager...")
    
    try:
        from core.manager import ConfigManager, get_config_manager
        
        # 测试配置管理器创建
        print("  📁 Testing config manager creation...")
        manager = ConfigManager()
        print(f"    ✅ Config manager created: {manager.VENUE}")
        
        # 测试全局配置管理器
        print("  📁 Testing global config manager...")
        global_manager = get_config_manager()
        print(f"    ✅ Global manager works: {global_manager.PRIMARY_SYMBOL}")
        
        # 测试配置属性访问
        print("  📁 Testing config property access...")
        print(f"    Venue: {manager.VENUE}")
        print(f"    Start Date: {manager.START_DATE}")
        print(f"    End Date: {manager.END_DATE}")
        print(f"    Main Timeframe: {manager.MAIN_TIMEFRAME}")
        print(f"    Primary Symbol: {manager.PRIMARY_SYMBOL}")
        print("    ✅ All properties accessible")
        
        # 测试回测配置构建
        print("  📁 Testing backtest config building...")
        backtest_config = manager.build_config()
        print(f"    ✅ Backtest config built: {len(backtest_config.instruments)} instruments")
        
        return True
        
    except Exception as e:
        print(f"    ❌ Config manager failed: {e}")
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """测试向后兼容性"""
    print("🧪 Testing backward compatibility...")
    
    try:
        # 测试导入现有settings模块
        print("  📁 Testing settings module import...")
        import core.settings as settings
        
        # 测试全局变量访问
        print("  📁 Testing global variables...")
        print(f"    VENUE: {settings.VENUE}")
        print(f"    START_DATE: {settings.START_DATE}")
        print(f"    END_DATE: {settings.END_DATE}")
        print(f"    PRIMARY_SYMBOL: {settings.PRIMARY_SYMBOL}")
        print("    ✅ Global variables accessible")
        
        # 测试函数调用
        print("  📁 Testing function calls...")
        data_cfg = settings.create_data_cfg("BTCUSDT", "1h", "main")
        print(f"    ✅ create_data_cfg works: {data_cfg.csv_file_name}")
        
        inst_cfg = settings.create_instrument_cfg("BTCUSDT")
        print(f"    ✅ create_instrument_cfg works: {inst_cfg.instrument_id}")
        
        # 测试build_config函数
        print("  📁 Testing build_config function...")
        config = settings.build_config()
        print(f"    ✅ build_config works: {config.start_date}")
        
        # 测试新增功能
        print("  📁 Testing new features...")
        envs = settings.get_available_environments()
        strategies = settings.get_available_strategies()
        print(f"    ✅ Available environments: {envs}")
        print(f"    ✅ Available strategies: {strategies}")
        
        return True
        
    except Exception as e:
        print(f"    ❌ Backward compatibility failed: {e}")
        traceback.print_exc()
        return False


def test_config_validation():
    """测试配置验证功能"""
    print("🧪 Testing configuration validation...")
    
    try:
        from core.loader import ConfigLoader
        
        loader = ConfigLoader()
        
        # 测试配置验证
        print("  📁 Testing config validation...")
        validation_report = loader.validate_config_files()
        
        if validation_report['valid']:
            print("    ✅ All configurations are valid")
        else:
            print("    ⚠️ Some configurations have issues:")
            for error in validation_report['errors']:
                print(f"      - {error}")
        
        print(f"    📊 Validation summary:")
        print(f"      Environments: {len(validation_report['environments'])}")
        print(f"      Strategies: {len(validation_report['strategies'])}")
        print(f"      Errors: {len(validation_report['errors'])}")
        print(f"      Warnings: {len(validation_report['warnings'])}")
        
        return validation_report['valid']
        
    except Exception as e:
        print(f"    ❌ Config validation failed: {e}")
        traceback.print_exc()
        return False


def test_config_switching():
    """测试配置切换功能"""
    print("🧪 Testing configuration switching...")
    
    try:
        import core.settings as settings
        
        # 记录原始配置
        original_env = settings._config_manager.active_config.environment
        original_strategy = settings._config_manager.active_config.strategy
        
        print(f"  📁 Original config: {original_env}/{original_strategy}")
        
        # 测试环境切换
        print("  📁 Testing environment switching...")
        if 'prod' in settings.get_available_environments():
            settings.switch_environment('prod')
            print(f"    ✅ Switched to prod: {settings.VENUE}")
            
            # 切换回原始环境
            settings.switch_environment(original_env)
            print(f"    ✅ Switched back to {original_env}")
        
        # 测试策略切换
        print("  📁 Testing strategy switching...")
        available_strategies = settings.get_available_strategies()
        if len(available_strategies) > 1:
            for strategy in available_strategies:
                if strategy != original_strategy:
                    settings.switch_strategy(strategy)
                    print(f"    ✅ Switched to strategy: {strategy}")
                    break
            
            # 切换回原始策略
            settings.switch_strategy(original_strategy)
            print(f"    ✅ Switched back to {original_strategy}")
        
        return True
        
    except Exception as e:
        print(f"    ❌ Config switching failed: {e}")
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("🚀 Starting Configuration System Tests")
    print("=" * 50)
    
    tests = [
        ("Config Loading", test_config_loading),
        ("Config Manager", test_config_manager),
        ("Backward Compatibility", test_backward_compatibility),
        ("Config Validation", test_config_validation),
        ("Config Switching", test_config_switching),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        
        try:
            result = test_func()
            results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
                
        except Exception as e:
            print(f"💥 {test_name} CRASHED: {e}")
            results.append((test_name, False))
    
    # 打印测试总结
    print("\n" + "=" * 50)
    print("📊 Test Results Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Configuration system is ready to use.")
        return 0
    else:
        print("⚠️ Some tests failed. Please check the configuration.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)