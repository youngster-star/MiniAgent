"""calculator：使用 AST 白名单求值，禁止 eval/exec 与任意函数调用"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable

from mini_agent.tools.base import ToolContext, ToolError

_BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_MAX_EXPRESSION = 200
_MAX_DEPTH = 20
_MAX_EXPONENT = 12
_MAX_RESULT_BITS = 10000


def calculator(context: ToolContext, arguments: dict[str, Any]) -> str:
    expression = arguments["expression"]
    if len(expression) > _MAX_EXPRESSION:
        raise ToolError("INVALID_ARGUMENTS", "表达式过长")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError("INVALID_ARGUMENTS", f"表达式语法错误：{exc.msg}") from exc

    try:
        value = _eval(tree.body, 0)
    except ZeroDivisionError as exc:
        raise ToolError("TOOL_EXECUTION_ERROR", "除数不能为 0") from exc
    except (OverflowError, ValueError) as exc:
        raise ToolError("TOOL_EXECUTION_ERROR", f"数值计算失败：{exc}") from exc
    return _format(value)


def _eval(node: ast.AST, depth: int) -> int | float:
    if depth > _MAX_DEPTH:
        raise ToolError("INVALID_ARGUMENTS", "表达式嵌套过深")

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("INVALID_ARGUMENTS", "只支持数字常量")
        _check_size(node.value)
        return node.value

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, depth + 1))

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _eval(node.left, depth + 1)
        right = _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_EXPONENT:
                raise ToolError("INVALID_ARGUMENTS", "指数绝对值不能超过 12")
        value = _BINARY[type(node.op)](left, right)
        _check_size(value)
        return value

    raise ToolError(
        "INVALID_ARGUMENTS", f"不支持的表达式节点：{type(node).__name__}"
    )


def _check_size(value: int | float) -> None:
    if isinstance(value, int) and value.bit_length() > _MAX_RESULT_BITS:
        raise ToolError("INVALID_ARGUMENTS", "计算结果过大")
    if isinstance(value, float) and not math.isfinite(value):
        raise ToolError("INVALID_ARGUMENTS", "计算结果不是有限数值")


def _format(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, ".12g")
    return str(value)