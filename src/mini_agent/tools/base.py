"""工具基础类型：运行上下文、工具规格、标准化结果与工具异常"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ToolError(Exception):
    """工具内部的可预期失败：由注册表转成 ToolResult"""

    def __init__(self,code:str,message:str) -> None:
        super().__init__(message)
        self.code = code

@dataclass(frozen=True)
class ToolContext:
    """工具执行上下文：工作区与输出上限"""

    workspace: Path
    max_output_chars: int = 20000

ToolFunc = Callable[[ToolContext,dict[str,Any]],str]

@dataclass(frozen=True)
class ToolSpec:
    """统一工具定义：元数据 + 参数 schema + 执行函数"""

    name:str
    description: str
    parameters: dict[str,Any]
    risk: str
    func: ToolFunc

    def openai_schema(self) -> dict[str,Any]:
        """转成 OpenAI 原生工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

@dataclass(frozen=True)
class ToolResult:
    """标准化工具结果：成功和失败使用统一结构"""

    tool: str
    status: str
    content: str
    error_code: str | None = None
    duration_ms: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "tool": self.tool,
                "status": self.status,
                "content": self.content,
                "error_code": self.error_code,
                "duration_ms": self.duration_ms,
            },
            ensure_ascii= False,
        )

def truncate_text(text:str,limit:int) -> str:
    """截断超长输出，保留明确标记"""
    if len(text) <= limit:
        return text
    marker = "\n...[truncated]"
    return text[:max(0,limit-len(marker))] + marker