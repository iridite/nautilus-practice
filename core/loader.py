"""
配置加载器

支持YAML配置文件的加载、解析和继承机制。
提供环境变量替换和配置验证功能。
"""

import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from .exceptions import ConfigValidationError
from .schemas import (
    ActiveConfig,
    ConfigPaths,
    EnvironmentConfig,
    StrategyConfig,
)


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.paths = ConfigPaths(config_dir)
        self._env_var_pattern = re.compile(r"\$\{([^}]+)\}")

    def load_environment_config(self, env_name: str) -> EnvironmentConfig:
        """
        加载环境配置，支持继承

        Args:
            env_name: 环境名称 (如 'dev', 'test', 'prod')

        Returns:
            EnvironmentConfig: 验证后的环境配置

        Raises:
            ConfigValidationError: 配置验证失败
            FileNotFoundError: 配置文件不存在
        """
        try:
            env_file = self.paths.get_environment_file(env_name)
            config_data = self._load_yaml_with_inheritance(env_file)

            # 环境变量替换
            config_data = self._substitute_env_vars(config_data)

            # 验证并创建配置对象
            return EnvironmentConfig(**config_data)

        except Exception as e:
            raise ConfigValidationError(
                f"Failed to load environment config '{env_name}': {str(e)}",
                field="environment",
                value=env_name,
            )

    def load_strategy_config(self, strategy_name: str) -> StrategyConfig:
        """
        加载策略配置

        Args:
            strategy_name: 策略名称

        Returns:
            StrategyConfig: 验证后的策略配置

        Raises:
            ConfigValidationError: 配置验证失败
            FileNotFoundError: 配置文件不存在
        """
        try:
            strategy_file = self.paths.get_strategy_file(strategy_name)
            config_data = self._load_yaml(strategy_file)

            # 环境变量替换
            config_data = self._substitute_env_vars(config_data)

            # 验证并创建配置对象
            return StrategyConfig(**config_data)

        except Exception as e:
            raise ConfigValidationError(
                f"Failed to load strategy config '{strategy_name}': {str(e)}",
                field="strategy",
                value=strategy_name,
            )

    def load_active_config(self) -> ActiveConfig:
        """
        加载当前活跃配置

        Returns:
            ActiveConfig: 验证后的活跃配置

        Raises:
            ConfigValidationError: 配置验证失败
            FileNotFoundError: 配置文件不存在
        """
        try:
            config_data = self._load_yaml(self.paths.active_file)

            # 环境变量替换
            config_data = self._substitute_env_vars(config_data)

            # 验证并创建配置对象
            return ActiveConfig(**config_data)

        except Exception as e:
            raise ConfigValidationError(
                f"Failed to load active config: {str(e)}", field="active_config"
            )

    def _load_yaml_with_inheritance(self, file_path: Path) -> Dict[str, Any]:
        """
        加载YAML文件，支持extends继承

        Args:
            file_path: YAML文件路径

        Returns:
            Dict[str, Any]: 合并后的配置数据
        """
        config_data = self._load_yaml(file_path)

        # 检查是否有继承
        if "extends" in config_data:
            parent_name = config_data["extends"]
            # 移除.yaml扩展名（如果存在）
            if parent_name.endswith(".yaml"):
                parent_name = parent_name[:-5]
            parent_file = self.paths.get_environment_file(parent_name)

            # 递归加载父配置
            parent_data = self._load_yaml_with_inheritance(parent_file)

            # 深度合并配置
            merged_data = self._deep_merge(parent_data, config_data)

            # 移除extends字段
            if "extends" in merged_data:
                del merged_data["extends"]

            return merged_data

        return config_data

    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """
        加载单个YAML文件

        Args:
            file_path: YAML文件路径

        Returns:
            Dict[str, Any]: 配置数据

        Raises:
            FileNotFoundError: 文件不存在
            yaml.YAMLError: YAML解析错误
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

                # 如果文件为空，返回空字典
                if not content.strip():
                    return {}

                data = yaml.safe_load(content)
                return data if data is not None else {}

        except yaml.YAMLError as e:
            raise ConfigValidationError(
                f"Invalid YAML syntax in {file_path}: {str(e)}", field="yaml_syntax"
            )
        except Exception as e:
            raise ConfigValidationError(
                f"Failed to read config file {file_path}: {str(e)}", field="file_access"
            )

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        深度合并两个字典

        Args:
            base: 基础字典
            override: 覆盖字典

        Returns:
            Dict[str, Any]: 合并后的字典
        """
        result = deepcopy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 递归合并嵌套字典
                result[key] = self._deep_merge(result[key], value)
            else:
                # 直接覆盖
                result[key] = deepcopy(value)

        return result

    def _substitute_env_vars(self, data: Union[Dict, List, str, Any]) -> Any:
        """
        递归替换配置中的环境变量

        支持格式：
        - ${VAR_NAME} - 必须存在的环境变量
        - ${VAR_NAME:default_value} - 带默认值的环境变量

        Args:
            data: 配置数据

        Returns:
            Any: 替换后的配置数据
        """
        if isinstance(data, dict):
            return {key: self._substitute_env_vars(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._substitute_env_vars(item) for item in data]
        elif isinstance(data, str):
            return self._substitute_string_env_vars(data)
        else:
            return data

    def _substitute_string_env_vars(self, text: str) -> str:
        """
        替换字符串中的环境变量

        Args:
            text: 包含环境变量的字符串

        Returns:
            str: 替换后的字符串
        """

        def replace_var(match) -> str:
            var_expr = match.group(1)

            # 检查是否有默认值
            if ":" in var_expr:
                var_name, default_value = var_expr.split(":", 1)
                result = os.environ.get(var_name.strip(), default_value.strip())
                return result if result is not None else default_value.strip()
            else:
                var_name = var_expr.strip()
                if var_name not in os.environ:
                    raise ConfigValidationError(
                        f"Required environment variable '{var_name}' not found",
                        field="environment_variable",
                        value=var_name,
                    )
                return os.environ[var_name]

        return self._env_var_pattern.sub(replace_var, text)

    def _validate_environment_configs(self, report: Dict[str, Any]):
        """验证所有环境配置"""
        for env_name in self.paths.list_environments():
            try:
                env_config = self.load_environment_config(env_name)
                report["environments"][env_name] = {"valid": True, "config": env_config}
            except Exception as e:
                report["valid"] = False
                report["errors"].append(f"Environment '{env_name}': {str(e)}")
                report["environments"][env_name] = {"valid": False, "error": str(e)}

    def _validate_strategy_configs(self, report: Dict[str, Any]):
        """验证所有策略配置"""
        for strategy_name in self.paths.list_strategies():
            try:
                strategy_config = self.load_strategy_config(strategy_name)
                report["strategies"][strategy_name] = {
                    "valid": True,
                    "config": strategy_config,
                }
            except Exception as e:
                report["valid"] = False
                report["errors"].append(f"Strategy '{strategy_name}': {str(e)}")
                report["strategies"][strategy_name] = {"valid": False, "error": str(e)}

    def _check_active_config_references(self, active_config, report: Dict[str, Any]):
        """检查活跃配置引用的环境和策略是否存在"""
        if active_config.environment not in report["environments"]:
            report["warnings"].append(
                f"Active config references unknown environment: {active_config.environment}"
            )

        if active_config.strategy not in report["strategies"]:
            report["warnings"].append(
                f"Active config references unknown strategy: {active_config.strategy}"
            )

    def _validate_active_config(self, report: Dict[str, Any]):
        """验证活跃配置"""
        try:
            active_config = self.load_active_config()
            report["active"] = {"valid": True, "config": active_config}
            self._check_active_config_references(active_config, report)
        except Exception as e:
            report["valid"] = False
            report["errors"].append(f"Active config: {str(e)}")
            report["active"] = {"valid": False, "error": str(e)}

    def validate_config_files(self) -> Dict[str, Any]:
        """
        验证所有配置文件的有效性

        Returns:
            Dict[str, Any]: 验证结果报告
        """
        report = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "environments": {},
            "strategies": {},
            "active": None,
        }

        self._validate_environment_configs(report)
        self._validate_strategy_configs(report)
        self._validate_active_config(report)

        return report


# 便利函数
def create_default_loader() -> ConfigLoader:
    """创建默认的配置加载器"""
    return ConfigLoader()


def load_config(
    env_name: str = "dev",
) -> tuple[EnvironmentConfig, StrategyConfig, ActiveConfig]:
    """
    便利函数：加载完整配置

    Args:
        env_name: 环境名称，如果不指定则从active.yaml读取

    Returns:
        tuple: (环境配置, 策略配置, 活跃配置)
    """
    loader = create_default_loader()

    # 首先加载活跃配置
    active_config = loader.load_active_config()

    # 使用指定的环境名称或活跃配置中的环境
    actual_env = env_name if env_name != "dev" else active_config.environment

    # 加载环境和策略配置
    env_config = loader.load_environment_config(actual_env)
    strategy_config = loader.load_strategy_config(active_config.strategy)

    return env_config, strategy_config, active_config


# 导出主要类和函数
__all__ = [
    "ConfigLoader",
    "create_default_loader",
    "load_config",
]
