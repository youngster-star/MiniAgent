"""工具注册表：查找、参数校验、权限校验、执行与结果标准化"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from mini_agent.tools.base import (
    ToolContext,
    ToolError,
    ToolResult,
    ToolSpec,
    truncate_text,
)
from mini_agent.tools.calculator import calculator
from mini_agent.tools.csv_tools import analyze_csv
from mini_agent.tools.file_tools import list_dir, read_file, write_file
from mini_agent.tools.validation import validate_arguments

logger = logging.getLogger(__name__)


def _build_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="calculator",
            description="计算数学表达式，支持 + - * / // % ** 与括号",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                    }
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
            risk="low",
            func=calculator,
        ),
        ToolSpec(
            name="read_file",
            description="读取工作区内的 UTF-8 文本文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 500},
                    "max_bytes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20000,
                        "default": 20000,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            risk="medium",
            func=read_file,
        ),
        ToolSpec(
            name="write_file",
            description="向工作区写入 UTF-8 文本文件；默认不覆盖",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 500},
                    "content": {"type": "string", "maxLength": 100000},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            risk="high",
            func=write_file,
        ),
        ToolSpec(
            name="list_dir",
            description="列出工作区内目录的直接子项",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                        "default": ".",
                    }
                },
                "additionalProperties": False,
            },
            risk="low",
            func=list_dir,
        ),
        ToolSpec(
            name="analyze_csv",
            description="读取 CSV，输出数值统计，并可按列降序展示前 N 行",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1, "maxLength": 500},
                    "sort_by": {"type": "string", "minLength": 1, "maxLength": 100},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 5,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            risk="medium",
            func=analyze_csv,
        ),
    )


class ToolRegistry:
    """ToolExecutor 的真实实现；循环只依赖 execute()"""

    def __init__(
        self, workspace: str | Path = "workspace", max_output_chars: int = 20000
    ) -> None:
        if max_output_chars <= 0:
            raise ValueError("max_output_chars 必须大于 0")
        root = Path(workspace).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._context = ToolContext(
            workspace=root, max_output_chars=max_output_chars
        )
        self._tools = {spec.name: spec for spec in _build_specs()}

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        started = time.perf_counter()
        spec = self._tools.get(name)
        if spec is None:
            return self._error(
                name, "TOOL_NOT_FOUND", f"工具未注册：{name}", started
            )

        try:
            normalized = validate_arguments(spec.parameters, arguments)
            content = spec.func(self._context, normalized)
        except ToolError as exc:
            return self._error(name, exc.code, str(exc), started)
        except Exception as exc:  # 工具内部异常不穿透循环
            logger.exception("tool %s failed", name)
            return self._error(
                name,
                "TOOL_EXECUTION_ERROR",
                f"{type(exc).__name__}: {exc}",
                started,
            )

        content = truncate_text(content, self._context.max_output_chars)
        return ToolResult(
            tool=name,
            status="success",
            content=content,
            duration_ms=_elapsed_ms(started),
        ).to_json()

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def describe(self) -> str:
        """生成系统提示中的工具清单，避免手写漂移"""
        lines = ["可用工具（只能使用以下工具）："]
        for spec in self._tools.values():
            schema = json.dumps(spec.parameters, ensure_ascii=False)
            lines.append(f"- {spec.name}（风险：{spec.risk}）：{spec.description}")
            lines.append(f"  参数 schema：{schema}")
        return "\n".join(lines)

    def _error(
        self, name: str, code: str, message: str, started: float
    ) -> str:
        return ToolResult(
            tool=name,
            status="error",
            content=message,
            error_code=code,
            duration_ms=_elapsed_ms(started),
        ).to_json()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)