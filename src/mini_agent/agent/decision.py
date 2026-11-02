"""把模型文本解析为内部 Decision；解析失败返回 invalid 不抛异常"""

from __future__ import annotations

import json
from dataclasses import dataclass,field
from enum import Enum
from typing import Any

class ActionType(str,Enum):
    """模型可以返回的决策类型"""

    FINAL = "final"
    TOOL_CALL = "tool_call"
    INVALID = "invalid"

@dataclass(frozen=True)
class Decision:
    """解析后的决策：invalid 时 error 保存可回灌的纠正原因"""

    type: ActionType
    thought: str = ""
    tool: str | None = None
    arguments: dict[str,Any] = field(default_factory=dict)
    content:str = ""
    error: str = ""
    raw:str = ""

def _invalid(reason:str,raw:str) -> Decision:
    return Decision(type=ActionType.INVALID,error=reason,raw=raw)

def _strip_code_fence(raw: str) -> str:
    """去掉模型偶尔添加的代码围栏：如 Markdown 代码围栏"""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 2:
        return text
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()

def parse_decision(raw:str) -> Decision:
    """解析模型输出：任何 格式问题 都转成 invalid，而不是中断循环"""
    if not isinstance(raw,str):
        return _invalid("模型相应 content 必须是字符串",str(raw))

    text = _strip_code_fence(raw)
    if not text:
        return _invalid("模型输出为空",raw)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return _invalid(f"不是合法 JSON ：{exc.msg}（第{exc.lineno}行第{exc.colno}列）",raw)

    if not isinstance(payload,dict):
        return _invalid("JSON 根节点必须是对象",raw)

    action_raw = payload.get("action")
    if not isinstance(action_raw,str):
        return _invalid("字段 action 缺失或不是字符串",raw)
    try:
        action = ActionType(action_raw)
    except ValueError:
        return _invalid(f"未知 action={action_raw!r}，只允许 final 或 tool_call",raw)
    if action is ActionType.INVALID:
        return _invalid("action 不能是 invalid",raw)

    thought = payload.get("thought","")
    if thought is None:
        thought = ""
    if not isinstance(thought,str):
        return _invalid("字段 thought 不是字符串",raw)

    if action is ActionType.FINAL:
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            return _invalid("action=final 时 content 必须是非空字符串", raw)
        return Decision(type=action, thought=thought, content=content, raw=raw)

    tool = payload.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return _invalid("action=tool_call 时 tool 必须是非空字符串", raw)

    arguments = payload.get("arguments",{})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments,dict):
        return _invalid("字段 arguments 必须是 JSON 对象",raw)

    return Decision(
        type=action,
        thought=thought,
        tool=tool,
        arguments=arguments,
        raw=raw
    )