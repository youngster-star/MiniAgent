"""JSON Schema 子集校验：只支持本项目工具用到的约束"""

from __future__ import annotations

from typing import Any

from mini_agent.tools.base import ToolError

def validate_arguments(schema:dict[str,Any],arguments: Any) -> dict[str,Any]:
    """校验并补齐默认值，失败统一抛 INVALID_ARGUMENTS"""
    if not isinstance(arguments,dict):
        raise ToolError("INVALID_ARGUMENTS","arguments 必须是 JSON 对象")

    properties = schema.get("properties",{})
    if not isinstance(properties,dict):
        raise ToolError("INVALID_ARGUMENTS", "工具 schema 配置错误：properties")

    for name in schema.get("required", []):
        if name not in arguments:
            raise ToolError("INVALID_ARGUMENTS", f"缺少必填参数：{name}")

    unknown = sorted(set(arguments) - set(properties))
    if unknown and not schema.get("additionalProperties", False):
        raise ToolError("INVALID_ARGUMENTS", f"未知参数：{', '.join(unknown)}")

    normalized = dict(arguments)
    for name, rule in properties.items():
        if name not in normalized:
            if "default" in rule:
                normalized[name] = rule["default"]
            continue
        normalized[name] = _validate_value(name,rule,normalized[name])
    return normalized

def _validate_value(name:str, rule:dict[str,Any], value:Any) -> Any:
    expected = rule.get("type")
    if expected and not _type_matches(expected,value):
        raise ToolError("INVALID_ARGUMENTS",
                        f"参数 {name} 类型错误：期望 {expected}，实际 {type(value).__name__}")

    if "enum" in rule and value not in rule["enum"]:
        raise ToolError( "INVALID_ARGUMENTS",
            f"参数 {name} 必须取 {rule['enum']} 之一，当前值：{value!r}")

    if isinstance(value,str):
        if len(value) < rule.get("minLength", 0):
            raise ToolError("INVALID_ARGUMENTS",
                            f"参数 {name} 长度不能小于 {rule['minLength']}")
        if "maxLength" in rule and len(value) > rule["maxLength"]:
            raise ToolError("INVALID_ARGUMENTS",
                            f"参数 {name} 长度不能超过 {rule['maxLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in rule and value < rule["minimum"]:
            raise ToolError("INVALID_ARGUMENTS",
                            f"参数 {name} 不能小于 {rule['minimum']}")
        if "maximum" in rule and value > rule["maximum"]:
            raise ToolError("INVALID_ARGUMENTS",
                            f"参数 {name} 不能大于 {rule['maximum']}")
    return value

def _type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False