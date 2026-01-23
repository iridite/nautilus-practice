"""
配置迁移工具

将现有的settings.py配置转换为新的YAML配置格式。
提供自动化迁移和验证功能。
"""

import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from .schemas import ConfigPaths
from .definitions import project_root


class ConfigMigrator:
    """配置迁移器"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.paths = ConfigPaths(config_dir)
        self.backup_dir = self.paths.config_root / "backup"
        self.backup_dir.mkdir(exist_ok=True)
    
    def migrate_from_settings(self, settings_module_path: str = "config.settings") -> Dict[str, Any]:
        """
        从现有的settings.py迁移配置
        
        Args:
            settings_module_path: settings模块路径
            
        Returns:
            Dict[str, Any]: 迁移报告
        """
        report = {
            'success': True,
            'errors': [],
            'warnings': [],
            'migrated_files': [],
            'backup_location': str(self.backup_dir)
        }
        
        try:
            # 动态导入settings模块
            import importlib
            settings = importlib.import_module(settings_module_path)
            
            # 备份现有配置文件
            self._backup_existing_configs()
            
            # 确保目录存在
            self.paths.ensure_directories()
            
            # 迁移环境配置
            self._migrate_environment_configs(settings, report)
            
            # 迁移策略配置
            self._migrate_strategy_configs(settings, report)
            
            # 迁移活跃配置
            self._migrate_active_config(settings, report)
            
            print("✅ Configuration migration completed successfully!")
            print(f"📁 Backup saved to: {self.backup_dir}")
            
        except Exception as e:
            report['success'] = False
            report['errors'].append(f"Migration failed: {str(e)}")
            print(f"❌ Migration failed: {str(e)}")
        
        return report
    
    def _backup_existing_configs(self):
        """备份现有的配置文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 备份现有的YAML文件（如果存在）
        for config_file in self.paths.config_root.glob("**/*.yaml"):
            if config_file.is_file():
                backup_file = self.backup_dir / f"{config_file.stem}_{timestamp}.yaml"
                backup_file.write_text(config_file.read_text())
    
    def _migrate_environment_configs(self, settings, report: Dict[str, Any]):
        """迁移环境配置"""
        try:
            # 创建基础环境配置
            base_config = {
                'trading': {
                    'venue': getattr(settings, 'VENUE', 'BINANCE'),
                    'instrument_type': getattr(settings, 'INSTRUMENT_TYPE', 'SWAP').value if hasattr(getattr(settings, 'INSTRUMENT_TYPE', 'SWAP'), 'value') else str(getattr(settings, 'INSTRUMENT_TYPE', 'SWAP')),
                    'initial_balance': float(getattr(settings, 'INITIAL_BALANCES', [100])[0].amount) if hasattr(getattr(settings, 'INITIAL_BALANCES', [100])[0], 'amount') else 100,
                    'currency': 'USDT'
                },
                'timeframes': {
                    'main': getattr(settings, 'MAIN_TIMEFRAME', '1h'),
                    'trend': getattr(settings, 'TREND_TIMEFRAME', '4h')
                },
                'backtest': {
                    'start_date': getattr(settings, 'START_DATE', '2025-12-01'),
                    'end_date': getattr(settings, 'END_DATE', '2025-12-30')
                },
                'logging': {
                    'level': 'INFO',
                    'file_level': 'DEBUG',
                    'components': {
                        'BacktestEngine': 'INFO',
                        'DataFeed': 'INFO',
                        'RSSqueezeStrategy': 'INFO'
                    },
                    'components_only': True
                }
            }
            
            # 写入基础配置
            base_file = self.paths.get_environment_file('base')
            self._write_yaml(base_file, base_config)
            report['migrated_files'].append(str(base_file))
            
            # 创建开发环境配置
            dev_config = {
                'extends': 'base.yaml',
                'backtest': {
                    'start_date': getattr(settings, 'START_DATE', '2025-12-01'),
                    'end_date': '2025-12-07'  # 开发环境使用更短周期
                },
                'logging': {
                    'level': 'DEBUG',
                    'file_level': 'DEBUG'
                },
                'trading': {
                    'initial_balance': 50  # 开发环境使用更小资金
                }
            }
            
            dev_file = self.paths.get_environment_file('dev')
            self._write_yaml(dev_file, dev_config)
            report['migrated_files'].append(str(dev_file))
            
            # 创建生产环境配置
            prod_config = {
                'extends': 'base.yaml',
                'logging': {
                    'level': 'WARNING',
                    'file_level': 'INFO'
                }
            }
            
            prod_file = self.paths.get_environment_file('prod')
            self._write_yaml(prod_file, prod_config)
            report['migrated_files'].append(str(prod_file))
            
        except Exception as e:
            report['errors'].append(f"Failed to migrate environment configs: {str(e)}")
    
    def _migrate_strategy_configs(self, settings, report: Dict[str, Any]):
        """迁移策略配置"""
        try:
            # 获取策略定义
            strategies = []
            
            # 尝试获取已定义的策略
            for attr_name in dir(settings):
                if attr_name.endswith('_STRATEGY') and not attr_name.startswith('_'):
                    strategy_obj = getattr(settings, attr_name)
                    if hasattr(strategy_obj, 'name') and hasattr(strategy_obj, 'module_path'):
                        strategies.append((attr_name, strategy_obj))
            
            # 迁移每个策略
            for strategy_name, strategy_obj in strategies:
                try:
                    strategy_config = self._extract_strategy_config(strategy_obj)
                    
                    # 确定策略文件名
                    if 'OIDivergence' in strategy_obj.name:
                        filename = 'oi_divergence'
                    elif 'RSSqueezeStrategy' in strategy_obj.name:
                        filename = 'rs_squeeze'
                    elif 'DualThrust' in strategy_obj.name:
                        filename = 'dual_thrust'
                    else:
                        filename = strategy_obj.name.lower().replace('strategy', '')
                    
                    strategy_file = self.paths.get_strategy_file(filename)
                    self._write_yaml(strategy_file, strategy_config)
                    report['migrated_files'].append(str(strategy_file))
                    
                except Exception as e:
                    report['warnings'].append(f"Failed to migrate strategy {strategy_name}: {str(e)}")
            
        except Exception as e:
            report['errors'].append(f"Failed to migrate strategy configs: {str(e)}")
    
    def _extract_strategy_config(self, strategy_obj) -> Dict[str, Any]:
        """提取策略配置"""
        config = {
            'name': strategy_obj.name,
            'module_path': strategy_obj.module_path,
            'parameters': {}
        }
        
        # 添加配置类名（如果有）
        if hasattr(strategy_obj, 'config_class'):
            config['config_class'] = strategy_obj.config_class
        
        # 提取参数
        if hasattr(strategy_obj, 'params'):
            params = strategy_obj.params
            if hasattr(params, '__dict__'):
                # 如果是对象，提取属性
                for key, value in params.__dict__.items():
                    if not key.startswith('_'):
                        config['parameters'][key] = self._convert_value(value)
            elif isinstance(params, dict):
                # 如果是字典，直接使用
                for key, value in params.items():
                    config['parameters'][key] = self._convert_value(value)
        
        return config
    
    def _migrate_active_config(self, settings, report: Dict[str, Any]):
        """迁移活跃配置"""
        try:
            active_config = {
                'environment': 'dev',
                'primary_symbol': getattr(settings, 'PRIMARY_SYMBOL', 'BTCUSDT')
            }
            
            # 确定当前活跃策略
            active_strategy = getattr(settings, 'ACTIVE_STRATEGY', None)
            if active_strategy and hasattr(active_strategy, 'name'):
                if 'OIDivergence' in active_strategy.name:
                    active_config['strategy'] = 'oi_divergence'
                elif 'RSSqueezeStrategy' in active_strategy.name:
                    active_config['strategy'] = 'rs_squeeze'
                elif 'DualThrust' in active_strategy.name:
                    active_config['strategy'] = 'dual_thrust'
                else:
                    active_config['strategy'] = 'rs_squeeze'  # 默认
            else:
                active_config['strategy'] = 'rs_squeeze'  # 默认
            
            # 添加覆盖配置示例
            active_config['overrides'] = {
                'backtest': {
                    'start_date': getattr(settings, 'START_DATE', '2025-12-15'),
                    'end_date': '2025-12-20'
                }
            }
            
            active_file = self.paths.active_file
            self._write_yaml(active_file, active_config)
            report['migrated_files'].append(str(active_file))
            
        except Exception as e:
            report['errors'].append(f"Failed to migrate active config: {str(e)}")
    
    def _convert_value(self, value) -> Any:
        """转换值为YAML兼容格式"""
        if isinstance(value, Decimal):
            return float(value)
        elif hasattr(value, 'value'):  # Enum类型
            return value.value
        elif hasattr(value, '__dict__'):  # 对象类型
            return {k: self._convert_value(v) for k, v in value.__dict__.items() if not k.startswith('_')}
        else:
            return value
    
    def _write_yaml(self, file_path: Path, data: Dict[str, Any]):
        """写入YAML文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)
    
    def validate_migration(self) -> Dict[str, Any]:
        """验证迁移结果"""
        from .loader import ConfigLoader
        
        loader = ConfigLoader(self.paths.config_root)
        return loader.validate_config_files()
    
    def create_migration_script(self) -> str:
        """创建迁移脚本"""
        script_content = '''#!/usr/bin/env python3
"""
配置迁移脚本

运行此脚本将现有的settings.py配置迁移到新的YAML格式。
"""

from config.migration import ConfigMigrator

def main():
    print("🚀 Starting configuration migration...")
    
    migrator = ConfigMigrator()
    report = migrator.migrate_from_settings()
    
    if report['success']:
        print("✅ Migration completed successfully!")
        print(f"📁 Migrated files: {len(report['migrated_files'])}")
        for file_path in report['migrated_files']:
            print(f"  - {file_path}")
        
        # 验证迁移结果
        print("\\n🔍 Validating migrated configuration...")
        validation_report = migrator.validate_migration()
        
        if validation_report['valid']:
            print("✅ All configurations are valid!")
        else:
            print("⚠️ Some configurations have issues:")
            for error in validation_report['errors']:
                print(f"  - {error}")
    else:
        print("❌ Migration failed!")
        for error in report['errors']:
            print(f"  - {error}")
    
    if report['warnings']:
        print("\\n⚠️ Warnings:")
        for warning in report['warnings']:
            print(f"  - {warning}")

if __name__ == "__main__":
    main()
'''
        
        script_path = project_root / "scripts" / "migrate_config.py"
        script_path.parent.mkdir(exist_ok=True)
        script_path.write_text(script_content)
        
        return str(script_path)


def create_migration_tool() -> ConfigMigrator:
    """创建配置迁移工具"""
    return ConfigMigrator()


# 便利函数
def migrate_settings(settings_module: str = "config.settings") -> Dict[str, Any]:
    """
    便利函数：迁移settings配置
    
    Args:
        settings_module: settings模块路径
        
    Returns:
        Dict[str, Any]: 迁移报告
    """
    migrator = create_migration_tool()
    return migrator.migrate_from_settings(settings_module)


# 导出主要类和函数
__all__ = [
    'ConfigMigrator',
    'create_migration_tool',
    'migrate_settings',
]