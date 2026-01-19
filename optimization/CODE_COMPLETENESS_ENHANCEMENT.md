# 代码完整性增强方案

## 问题描述

在优化流程中，AI 生成的策略代码存在以下问题：

1. **代码不完整**：只生成部分代码，缺少关键方法的实现
2. **使用占位符**：方法体只有 `pass` 或 `...`，没有实际逻辑
3. **过度简化**：省略大量代码，使用 `# ... 其他代码 ...` 等注释
4. **代码过短**：生成的代码只有几百字符，而完整策略通常需要 8000+ 字符
5. **方法缺失**：关键方法如 `on_bar`、`on_start` 等缺少实现
6. **转义字符问题**：返回 `\n` 字面字符串而非真正的换行符

这些问题导致生成的代码无法直接运行，影响优化流程的自动化。

## 解决方案概览

### 三层防护机制

```
┌─────────────────────────────────────┐
│  1. Prompt 强化（预防层）            │
│  - 明确代码长度要求（8000-15000字符）│
│  - 明确方法数量要求（10+个方法）     │
│  - 提供正确/错误示例                 │
│  - 强调不能使用占位符                │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  2. 代码提取验证（检测层）           │
│  - 修复转义字符                      │
│  - 基础结构检查                      │
│  - 代码长度验证                      │
│  - 类和方法存在性检查                │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  3. 深度完整性检查（验证层）         │
│  - 占位符方法检测                    │
│  - 关键方法逻辑充分性检查            │
│  - 策略组件完整性验证                │
│  - 方法数量统计                      │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  4. 智能重试机制（修复层）           │
│  - 最多重试 3 次                     │
│  - 每次失败后详细说明原因            │
│  - 逐步增强要求的严格度              │
│  - 最终失败保护原始代码              │
└─────────────────────────────────────┘
```

## 实现的增强措施

### 1. Prompt 强化 (`optimization/prompts/researcher.py`)

#### 参数微调模式增强
```python
**重要：输出格式要求**:
1. 代码总长度必须在 8000-15000 字符之间
2. 代码总行数应该在 300-600 行之间
3. 必须包含所有 60+ 个配置参数
4. 必须包含所有 10+ 个方法的完整实现
5. __init__ 方法至少需要 15 行实际代码
6. on_bar 方法至少需要 10 行实际代码
7. 不能使用 pass、... 或 "# TODO" 占位符
8. 不能使用 "# ... 其他代码 ..." 省略标记
```

#### 逻辑重构模式增强
```python
**重要：输出格式要求**:
1. 代码总长度必须在 8000-15000 字符之间
2. 代码总行数应该在 300-600 行之间
3. 所有方法都必须有完整实现（每个至少5-10行代码）
4. __init__ 方法至少需要 20 行实际代码
5. on_bar 方法至少需要 15 行实际代码
6. 所有辅助方法都必须有完整实现
```

#### 提供明确示例
- ✅ 正确示例：完整的策略代码（8000+ 字符）
- ❌ 错误示例：只有注释、只有占位符、代码过短

### 2. 代码提取验证增强 (`optimization/utils/code_parser.py`)

#### 转义字符自动修复
```python
# 检测 \n 字面字符串并自动转换为真正的换行符
if escaped_newlines > actual_newlines * 2:
    code = code.replace("\\n", "\n")
    code = code.replace("\\t", "    ")
```

#### 基础验证检查
- ✅ 代码长度 >= 500 字符
- ✅ 包含 import 语句
- ✅ 包含 Config 类定义
- ✅ 包含 Strategy 类定义
- ✅ 包含 __init__ 方法
- ✅ 包含 on_start 和 on_bar 方法
- ✅ 非注释代码占比 > 10%

### 3. 深度完整性检查 (`check_code_completeness()`)

#### 代码长度检查
```python
if len(code) < 3000:
    return {
        "is_complete": False,
        "reason": "代码过短（完整策略通常至少3000字符）"
    }
```

#### 占位符方法检测
```python
# 检测: def method(): \n    pass 或 def method(): \n    ...
method_pattern = r"def\s+(\w+)\s*\([^)]*\):\s*\n\s+(?:pass|\.\.\.)\s*(?:\n|$)"
placeholder_methods = re.findall(method_pattern, code)
```

#### 关键方法逻辑充分性检查
```python
critical_methods = {
    "on_bar": r"def\s+on_bar\s*\([^)]*\):\s*\n((?:\s+.+\n){5,})",      # 至少5行
    "on_start": r"def\s+on_start\s*\([^)]*\):\s*\n((?:\s+.+\n){3,})",  # 至少3行
    "__init__": r"def\s+__init__\s*\([^)]*\):\s*\n((?:\s+.+\n){10,})", # 至少10行
}
```

#### 策略组件完整性验证
```python
required_components = {
    "indicators": ["BollingerBands", "KeltnerChannel", "AverageTrueRange", ...],
    "data_structures": ["deque", "Dict", "Optional"],
    "trading_operations": ["submit_order", "cancel_all_orders"],
}
```

#### 方法数量统计
```python
method_count = len(re.findall(r"def\s+\w+\s*\(", code))
if method_count < 8:
    return {"is_complete": False, "reason": "方法数量过少"}
```

### 4. 智能重试机制 (`optimization/nodes/researcher.py`)

#### 重试流程
```python
max_retries = 3
for attempt in range(max_retries):
    # 1. 调用 AI 生成代码
    response = model.invoke(...)
    
    # 2. 预处理：修复转义字符
    if "\\n" in response_content:
        response_content = response_content.replace("\\n", "\n")
    
    # 3. 提取代码并验证
    new_code = extract_code(response_content)
    is_valid, error_msg = validate_strategy_code(new_code)
    
    # 4. 如果验证失败，增强 prompt 并重试
    if not is_valid:
        user_msg_parts.append(
            f"⚠️ 上次生成失败，原因: {error_msg}\n"
            "代码长度: {len(new_code)} 字符\n"
            "**请务必返回完整的策略代码**...\n"
            "原始代码长度: {len(current_code)} 字符作为参考\n"
        )
        continue
    
    # 5. 验证通过，返回代码
    return new_code

# 6. 最终失败，保护原始代码
return current_code
```

#### 详细的验证反馈
```python
print(f"\n✅ 新策略代码已生成并验证通过")
print(f"   - 代码长度: {len(new_code)} 字符")
print(f"   - 代码行数: {len(code_lines)} 行")
print(f"   - 类定义数: {class_count} 个")
print(f"   - 方法数量: {method_count} 个")
print(f"   - Import语句: {import_count} 个")
print("   - 包含 Config 类: ✓")
print("   - 包含 Strategy 类: ✓")
print("   - 包含关键方法: ✓")
print("   - 代码完整性检查: ✓\n")
```

## 验证结果

### 测试用例

#### 测试 1: 代码过短
```python
short_code = """
import json
class Config(BaseStrategyConfig):
    param1: int = 10
class Strategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
"""
# 结果: ❌ 代码过短（163字符），完整策略通常至少3000字符
```

#### 测试 2: 包含占位符
```python
# 包含 def on_bar(): pass 等占位符方法
# 结果: ❌ 发现占位符方法: on_bar, on_start。请提供完整实现
```

#### 测试 3: 方法逻辑不足
```python
# on_bar 方法只有 1-2 行代码
# 结果: ❌ 方法 on_bar 缺少足够的实现逻辑
```

#### 测试 4: 方法数量不足
```python
# 只有 3-4 个方法
# 结果: ❌ 方法数量过少（4个）。完整策略通常包含10+个方法
```

#### 测试 5: 完整策略
```python
# 8000+ 字符，10+ 方法，所有方法都有完整实现
# 结果: ✅ 代码完整性检查通过
```

## 使用指南

### 自动运行

修改已集成到优化流程，无需手动干预：

```bash
# 正常运行优化流程
python optimize_strategy.py
```

系统会自动：
1. 检测 AI 返回的代码格式
2. 修复转义字符
3. 验证代码完整性
4. 失败时自动重试（最多3次）
5. 提供详细的验证信息
6. 最终失败时保护原始代码

### 监控日志

关注以下关键日志信息：

```
🤖 调用 AI 生成策略代码 (尝试 1/3)...
⚠️ 检测到 AI 返回内容包含转义字符，正在修复...
✅ 已修复转义字符

✅ 新策略代码已生成并验证通过
   - 代码长度: 12458 字符
   - 代码行数: 456 行
   - 类定义数: 2 个
   - 方法数量: 15 个
   - Import语句: 12 个
   - 包含 Config 类: ✓
   - 包含 Strategy 类: ✓
   - 包含关键方法: ✓
   - 代码完整性检查: ✓
```

失败时的日志：

```
⚠️ 代码验证失败: 方法 on_bar 缺少足够的实现逻辑
   代码长度: 2345 字符
   代码行数: 89 行
🔄 重试中...

🤖 调用 AI 生成策略代码 (尝试 2/3)...
⚠️ 上次生成失败，原因: 方法 on_bar 缺少足够的实现逻辑
...
```

## 技术细节

### 完整性检查算法

```python
def check_code_completeness(code: str) -> Dict[str, Any]:
    # 1. 长度检查（快速失败）
    if len(code) < 3000:
        return fail("代码过短")
    
    # 2. 占位符检测（正则匹配）
    if has_placeholder_methods(code):
        return fail("发现占位符方法")
    
    # 3. 关键方法逻辑检查（行数统计）
    for method in ["__init__", "on_start", "on_bar"]:
        if not has_sufficient_logic(code, method):
            return fail(f"{method} 逻辑不足")
    
    # 4. 组件完整性检查（关键词搜索）
    if not has_required_components(code):
        return fail("缺少关键组件")
    
    # 5. 方法数量检查（计数）
    if method_count(code) < 8:
        return fail("方法数量不足")
    
    return success("完整性检查通过")
```

### 正则表达式说明

#### 占位符方法检测
```python
# 匹配: def method_name(...): \n    pass
pattern = r"def\s+(\w+)\s*\([^)]*\):\s*\n\s+(?:pass|\.\.\.)\s*(?:\n|$)"
```

#### 方法逻辑充分性检查
```python
# 匹配: def on_bar(...): 后面至少有5行代码
pattern = r"def\s+on_bar\s*\([^)]*\):\s*\n((?:\s+.+\n){5,})"
```

### 重试策略

```
尝试 1: 使用标准 prompt
  ↓ (失败)
尝试 2: prompt + 失败原因 + 基础要求
  ↓ (失败)
尝试 3: prompt + 失败原因 + 详细要求 + 原始代码参考
  ↓ (失败)
返回原始代码（保护性措施）
```

## 优化效果预期

### 之前（无完整性检查）
- ❌ 代码完整率: ~30%
- ❌ 需要手动修复: 70% 的情况
- ❌ 包含占位符: 40% 的情况
- ❌ 代码过短: 50% 的情况

### 之后（有完整性检查）
- ✅ 代码完整率: ~90%
- ✅ 需要手动修复: ~10% 的情况
- ✅ 包含占位符: <5% 的情况
- ✅ 代码过短: <5% 的情况

## 配置参数

### 代码长度要求
```python
MIN_CODE_LENGTH = 500      # 基础验证最小长度
IDEAL_CODE_LENGTH = 3000   # 深度检查最小长度
RECOMMENDED_MIN = 8000     # 推荐最小长度
RECOMMENDED_MAX = 15000    # 推荐最大长度
```

### 方法行数要求
```python
MIN_INIT_LINES = 10        # __init__ 最少行数
MIN_ON_START_LINES = 3     # on_start 最少行数
MIN_ON_BAR_LINES = 5       # on_bar 最少行数
MIN_METHOD_COUNT = 8       # 最少方法数量
```

### 重试配置
```python
MAX_RETRIES = 3            # 最大重试次数
```

## 相关文件

- `optimization/utils/code_parser.py` - 代码提取和完整性验证
- `optimization/nodes/researcher.py` - AI 调用和重试逻辑
- `optimization/prompts/researcher.py` - 强化的 System Prompt
- `optimization/CODE_COMPLETENESS_ENHANCEMENT.md` - 本文档

## 故障排查

### 问题：AI 仍然返回不完整代码

**原因**：
1. Prompt 可能需要进一步优化
2. AI 模型容量不足
3. 输入的回测数据过长，挤压了输出空间

**解决方案**：
1. 检查 prompt 是否正确加载
2. 尝试使用更大的模型
3. 精简回测报告，只保留关键信息

### 问题：验证总是失败

**原因**：
1. 验证规则过于严格
2. 原始策略代码本身不符合规范

**解决方案**：
1. 调整 `code_parser.py` 中的验证阈值
2. 修复原始策略代码，使其符合规范

### 问题：生成的代码有语法错误

**原因**：
1. AI 生成了错误的代码
2. 转义字符修复不完全

**解决方案**：
1. 使用 `ast.parse()` 进行语法检查（后续增强）
2. 增强转义字符检测逻辑

## 后续优化方向

1. **语法检查**：集成 `ast.parse()` 进行 Python 语法验证
2. **类型检查**：验证类继承关系是否正确
3. **导入检查**：验证所有使用的类是否已导入
4. **代码质量检查**：集成 pylint 或 flake8
5. **智能代码补全**：当代码不完整时，尝试自动补全
6. **版本对比**：对比生成的代码与原始代码的差异

## 更新日志

### v1.0 (2024-01-XX)
- ✅ 实现三层验证机制
- ✅ 添加深度完整性检查
- ✅ 实现智能重试机制
- ✅ 强化 Prompt 模板
- ✅ 添加详细的验证反馈

## 总结

通过实施**三层防护 + 智能重试**机制，我们显著提高了 AI 生成代码的完整性和可用性：

1. **预防**：通过强化的 Prompt 明确要求
2. **检测**：通过基础验证快速发现问题
3. **验证**：通过深度检查确保代码质量
4. **修复**：通过智能重试自动改进
5. **保护**：失败时保护原始代码

这套机制确保了优化流程的自动化和稳定性，大大减少了人工干预的需求。