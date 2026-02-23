"""
配置验证增强模块

提供更严格的配置验证，检测常见的配置错误：
- YAML 中的字段名与 Pydantic 模型不匹配
- 使用了默认值但 YAML 中未明确指定
- 字段名拼写错误或位置错误
"""

from typing import Any, Dict, List, Set
from pydantic import BaseModel


class ConfigValidationWarning:
    """配置验证警告"""

    def __init__(self, field: str, message: str, suggestion: str = ""):
        self.field = field
        self.message = message
        self.suggestion = suggestion

    def __str__(self):
        result = f"⚠️  {self.field}: {self.message}"
        if self.suggestion:
            result += f"\n   建议: {self.suggestion}"
        return result


class StrictConfigValidator:
    """严格的配置验证器"""

    @staticmethod
    def get_model_fields(model: type[BaseModel]) -> Set[str]:
        """获取 Pydantic 模型的所有字段名"""
        return set(model.model_fields.keys())

    @staticmethod
    def get_nested_model_fields(model: type[BaseModel]) -> Dict[str, type[BaseModel]]:
        """获取嵌套模型的字段名和类型"""
        nested = {}
        for field_name, field_info in model.model_fields.items():
            annotation = field_info.annotation
            # 检查是否是 BaseModel 子类
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                nested[field_name] = annotation
        return nested

    @staticmethod
    def find_unknown_fields(
        yaml_data: Dict[str, Any], model: type[BaseModel]
    ) -> List[ConfigValidationWarning]:
        """查找 YAML 中存在但模型中不存在的字段"""
        warnings = []
        model_fields = StrictConfigValidator.get_model_fields(model)
        nested_fields = StrictConfigValidator.get_nested_model_fields(model)

        for yaml_key, yaml_value in yaml_data.items():
            if yaml_key not in model_fields:
                # 字段不存在于模型中
                suggestion = StrictConfigValidator._suggest_field_name(yaml_key, model_fields)
                warnings.append(
                    ConfigValidationWarning(
                        field=yaml_key,
                        message=f"字段 '{yaml_key}' 在模型中不存在，将被忽略",
                        suggestion=suggestion,
                    )
                )
            elif yaml_key in nested_fields and isinstance(yaml_value, dict):
                # 递归检查嵌套字段
                nested_model = nested_fields[yaml_key]
                nested_warnings = StrictConfigValidator.find_unknown_fields(
                    yaml_value, nested_model
                )
                for warning in nested_warnings:
                    warning.field = f"{yaml_key}.{warning.field}"
                    warnings.append(warning)

        return warnings

    @staticmethod
    def find_missing_required_fields(
        yaml_data: Dict[str, Any], model: type[BaseModel]
    ) -> List[ConfigValidationWarning]:
        """查找模型中必需但 YAML 中缺失的字段（没有默认值的字段）"""
        warnings = []
        nested_fields = StrictConfigValidator.get_nested_model_fields(model)

        for field_name, field_info in model.model_fields.items():
            # 检查字段是否必需（没有默认值）
            if field_info.is_required() and field_name not in yaml_data:
                warnings.append(
                    ConfigValidationWarning(
                        field=field_name,
                        message=f"必需字段 '{field_name}' 在 YAML 中缺失",
                        suggestion=f"请在配置文件中添加 '{field_name}' 字段",
                    )
                )
            # 递归检查嵌套字段
            elif field_name in nested_fields and field_name in yaml_data:
                if isinstance(yaml_data[field_name], dict):
                    nested_model = nested_fields[field_name]
                    nested_warnings = StrictConfigValidator.find_missing_required_fields(
                        yaml_data[field_name], nested_model
                    )
                    for warning in nested_warnings:
                        warning.field = f"{field_name}.{warning.field}"
                        warnings.append(warning)

        return warnings

    @staticmethod
    def find_fields_using_defaults(
        yaml_data: Dict[str, Any], model: type[BaseModel], important_fields: Set[str]
    ) -> List[ConfigValidationWarning]:
        """查找使用了默认值的重要字段"""
        warnings = []
        nested_fields = StrictConfigValidator.get_nested_model_fields(model)

        for field_name in important_fields:
            if field_name not in yaml_data:
                field_info = model.model_fields.get(field_name)
                if field_info and not field_info.is_required():
                    default_value = field_info.default
                    warnings.append(
                        ConfigValidationWarning(
                            field=field_name,
                            message=f"重要字段 '{field_name}' 未在 YAML 中指定，使用默认值: {default_value}",
                            suggestion=f"建议在配置文件中明确指定 '{field_name}' 的值",
                        )
                    )
            # 递归检查嵌套字段
            elif "." in field_name:
                parent, child = field_name.split(".", 1)
                if parent in nested_fields and parent in yaml_data:
                    if isinstance(yaml_data[parent], dict):
                        nested_model = nested_fields[parent]
                        nested_warnings = StrictConfigValidator.find_fields_using_defaults(
                            yaml_data[parent], nested_model, {child}
                        )
                        for warning in nested_warnings:
                            warning.field = f"{parent}.{warning.field}"
                            warnings.append(warning)

        return warnings

    @staticmethod
    def _suggest_field_name(wrong_name: str, valid_names: Set[str]) -> str:
        """使用编辑距离算法建议正确的字段名"""

        def levenshtein_distance(s1: str, s2: str) -> int:
            """计算两个字符串的编辑距离"""
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)

            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row

            return previous_row[-1]

        # 找到编辑距离最小的字段名
        suggestions = []
        for valid_name in valid_names:
            distance = levenshtein_distance(wrong_name.lower(), valid_name.lower())
            if distance <= 3:  # 只建议编辑距离 <= 3 的字段
                suggestions.append((distance, valid_name))

        if suggestions:
            suggestions.sort(key=lambda x: x[0])
            best_matches = [name for _, name in suggestions[:3]]
            return f"你是否想使用: {', '.join(best_matches)}?"
        return ""

    @staticmethod
    def validate_config(
        yaml_data: Dict[str, Any],
        model: type[BaseModel],
        important_fields: Set[str] | None = None,
    ) -> List[ConfigValidationWarning]:
        """
        全面验证配置

        Args:
            yaml_data: YAML 配置数据
            model: Pydantic 模型类
            important_fields: 重要字段集合（应该明确指定而非使用默认值）

        Returns:
            List[ConfigValidationWarning]: 验证警告列表
        """
        warnings = []

        # 1. 查找未知字段
        warnings.extend(StrictConfigValidator.find_unknown_fields(yaml_data, model))

        # 2. 查找缺失的必需字段
        warnings.extend(StrictConfigValidator.find_missing_required_fields(yaml_data, model))

        # 3. 查找使用默认值的重要字段
        if important_fields:
            warnings.extend(
                StrictConfigValidator.find_fields_using_defaults(yaml_data, model, important_fields)
            )

        return warnings
