#!/usr/bin/env python3
"""
配置管理CLI工具

提供命令行界面来管理配置系统，包括验证、切换、查看等功能。
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent  # scripts目录的父目录
sys.path.insert(0, str(project_root))


def cmd_validate(args):
    """验证配置文件"""
    try:
        import config.settings as settings
        
        print("🔍 验证配置文件...")
        report = settings.validate_config()
        
        if report['valid']:
            print("✅ 所有配置文件都有效!")
            print(f"📊 环境配置: {len(report['environments'])} 个")
            print(f"📊 策略配置: {len(report['strategies'])} 个")
        else:
            print("❌ 配置验证失败:")
            for error in report['errors']:
                print(f"  - {error}")
            
            if report['warnings']:
                print("\n⚠️ 警告:")
                for warning in report['warnings']:
                    print(f"  - {warning}")
            
            return 1
        
        return 0
        
    except Exception as e:
        print(f"💥 验证过程出错: {e}")
        return 1


def cmd_list(args):
    """列出可用的环境和策略"""
    try:
        import config.settings as settings
        
        print("📋 可用配置:")
        print("-" * 30)
        
        # 列出环境
        environments = settings.get_available_environments()
        current_env = settings.get_active_config().environment
        print(f"🌍 环境 ({len(environments)} 个):")
        for env in environments:
            marker = " ← 当前" if env == current_env else ""
            print(f"  - {env}{marker}")
        
        # 列出策略
        strategies = settings.get_available_strategies()
        current_strategy = settings.get_active_config().strategy
        print(f"\n🎯 策略 ({len(strategies)} 个):")
        for strategy in strategies:
            marker = " ← 当前" if strategy == current_strategy else ""
            print(f"  - {strategy}{marker}")
        
        return 0
        
    except Exception as e:
        print(f"💥 列出配置时出错: {e}")
        return 1


def cmd_show(args):
    """显示当前配置"""
    try:
        import config.settings as settings
        
        print("📋 当前配置摘要:")
        print("=" * 40)
        settings.print_config_summary()
        
        if args.detail:
            print("\n🔧 配置系统信息:")
            print("-" * 30)
            info = settings.get_config_system_info()
            for key, value in info.items():
                print(f"  {key}: {value}")
        
        return 0
        
    except Exception as e:
        print(f"💥 显示配置时出错: {e}")
        return 1


def cmd_switch(args):
    """切换环境或策略"""
    try:
        import config.settings as settings
        
        if args.environment:
            print(f"🔄 切换到环境: {args.environment}")
            available_envs = settings.get_available_environments()
            
            if args.environment not in available_envs:
                print(f"❌ 环境 '{args.environment}' 不存在")
                print(f"可用环境: {', '.join(available_envs)}")
                return 1
            
            settings.switch_environment(args.environment)
            print(f"✅ 已切换到环境: {args.environment}")
        
        if args.strategy:
            print(f"🔄 切换到策略: {args.strategy}")
            available_strategies = settings.get_available_strategies()
            
            if args.strategy not in available_strategies:
                print(f"❌ 策略 '{args.strategy}' 不存在")
                print(f"可用策略: {', '.join(available_strategies)}")
                return 1
            
            settings.switch_strategy(args.strategy)
            print(f"✅ 已切换到策略: {args.strategy}")
        
        if not args.environment and not args.strategy:
            print("❌ 请指定要切换的环境 (--env) 或策略 (--strategy)")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"💥 切换配置时出错: {e}")
        return 1


def cmd_test(args):
    """测试配置系统"""
    try:
        print("🧪 运行配置系统测试...")
        
        # 运行测试脚本
        import subprocess
        result = subprocess.run([
            sys.executable, "test_config_system.py"
        ], cwd=project_root, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ 所有测试通过!")
            if args.verbose:
                print("\n📋 测试输出:")
                print(result.stdout)
        else:
            print("❌ 测试失败!")
            print("\n📋 错误输出:")
            print(result.stderr)
            if args.verbose:
                print("\n📋 完整输出:")
                print(result.stdout)
        
        return result.returncode
        
    except Exception as e:
        print(f"💥 运行测试时出错: {e}")
        return 1


def cmd_migrate(args):
    """迁移现有配置"""
    try:
        from config.migration import migrate_settings
        
        print("🚀 开始配置迁移...")
        
        if args.backup:
            print("📁 创建备份...")
        
        report = migrate_settings()
        
        if report['success']:
            print("✅ 迁移成功!")
            print(f"📁 迁移的文件: {len(report['migrated_files'])} 个")
            
            if args.verbose:
                for file_path in report['migrated_files']:
                    print(f"  - {file_path}")
            
            print(f"📁 备份位置: {report['backup_location']}")
        else:
            print("❌ 迁移失败!")
            for error in report['errors']:
                print(f"  - {error}")
        
        if report['warnings']:
            print("\n⚠️ 警告:")
            for warning in report['warnings']:
                print(f"  - {warning}")
        
        return 0 if report['success'] else 1
        
    except Exception as e:
        print(f"💥 迁移过程出错: {e}")
        return 1


def cmd_reload(args):
    """重新加载配置"""
    try:
        import config.settings as settings
        
        print("🔄 重新加载配置...")
        settings.reload_config()
        print("✅ 配置重新加载完成!")
        
        if args.show:
            print("\n📋 当前配置:")
            settings.print_config_summary()
        
        return 0
        
    except Exception as e:
        print(f"💥 重新加载配置时出错: {e}")
        return 1


def cmd_init(args):
    """初始化配置系统"""
    try:
        from config.schemas import ConfigPaths
        
        print("🚀 初始化配置系统...")
        
        # 确保配置目录存在
        paths = ConfigPaths()
        paths.ensure_directories()
        
        print(f"📁 配置目录: {paths.config_root}")
        print(f"📁 环境配置: {paths.environments_dir}")
        print(f"📁 策略配置: {paths.strategies_dir}")
        
        # 检查必要文件是否存在
        required_files = [
            paths.get_environment_file('base'),
            paths.get_environment_file('dev'),
            paths.active_file
        ]
        
        missing_files = [f for f in required_files if not f.exists()]
        
        if missing_files:
            print("\n⚠️ 缺少必要的配置文件:")
            for file_path in missing_files:
                print(f"  - {file_path}")
            print("\n💡 请运行迁移工具或手动创建配置文件")
        else:
            print("✅ 配置系统初始化完成!")
        
        return 0
        
    except Exception as e:
        print(f"💥 初始化过程出错: {e}")
        return 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="配置管理CLI工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s validate                    # 验证所有配置文件
  %(prog)s list                        # 列出可用的环境和策略
  %(prog)s show                        # 显示当前配置
  %(prog)s switch --env prod           # 切换到生产环境
  %(prog)s switch --strategy oi_divergence  # 切换策略
  %(prog)s test                        # 运行配置系统测试
  %(prog)s migrate                     # 迁移现有配置
  %(prog)s reload                      # 重新加载配置
  %(prog)s init                        # 初始化配置系统
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # validate 命令
    parser_validate = subparsers.add_parser('validate', help='验证配置文件')
    parser_validate.set_defaults(func=cmd_validate)
    
    # list 命令
    parser_list = subparsers.add_parser('list', help='列出可用的环境和策略')
    parser_list.set_defaults(func=cmd_list)
    
    # show 命令
    parser_show = subparsers.add_parser('show', help='显示当前配置')
    parser_show.add_argument('--detail', action='store_true', help='显示详细信息')
    parser_show.set_defaults(func=cmd_show)
    
    # switch 命令
    parser_switch = subparsers.add_parser('switch', help='切换环境或策略')
    parser_switch.add_argument('--env', '--environment', dest='environment', help='切换到指定环境')
    parser_switch.add_argument('--strategy', help='切换到指定策略')
    parser_switch.set_defaults(func=cmd_switch)
    
    # test 命令
    parser_test = subparsers.add_parser('test', help='测试配置系统')
    parser_test.add_argument('--verbose', '-v', action='store_true', help='显示详细输出')
    parser_test.set_defaults(func=cmd_test)
    
    # migrate 命令
    parser_migrate = subparsers.add_parser('migrate', help='迁移现有配置')
    parser_migrate.add_argument('--backup', action='store_true', help='创建备份')
    parser_migrate.add_argument('--verbose', '-v', action='store_true', help='显示详细输出')
    parser_migrate.set_defaults(func=cmd_migrate)
    
    # reload 命令
    parser_reload = subparsers.add_parser('reload', help='重新加载配置')
    parser_reload.add_argument('--show', action='store_true', help='显示重新加载后的配置')
    parser_reload.set_defaults(func=cmd_reload)
    
    # init 命令
    parser_init = subparsers.add_parser('init', help='初始化配置系统')
    parser_init.set_defaults(func=cmd_init)
    
    # 解析参数
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # 执行命令
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断操作")
        return 1
    except Exception as e:
        print(f"💥 执行命令时出错: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)