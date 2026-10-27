"""把供应商返回的JSON解析为内部统一结构"""

from __future__ import annotations

from dataclasses import dataclass,field
from typing import Any

class LLMProtocolError(Exception):
    """响应结构不符合预期"""
@dataclass(frozen=True)
class LLMResponse:
    content: str        # 响应内容
    tool_calls: list[dict[str,Any]] = field(default_factory=list)  # 工具调用列表
    usage: dict[str,Any] = field(default_factory=dict)  # 使用情况
    raw: dict[str,Any] = field(default_factory=dict)  # 原始响应

def parse_chat_completion(payload:Any) -> LLMResponse:      # payload: 供应商返回的JSON
    """解析 OpenAI 兼容的 chat completions 响应"""
    if not isinstance(payload,dict):
        raise LLMProtocolError("响应根节点必须是 JSON 对象")

    choices = payload.get("choices")
    if not isinstance(choices,list) or not choices:
        raise LLMProtocolError("响应缺少非空 choices 数组")

    first = choices[0]
    if not isinstance(first,dict):
        raise LLMProtocolError("choices[0] 必须是对象")

    message = first.get("message")
    if not isinstance(message,dict):
        raise LLMProtocolError("choices[0].message 必须是对象")

    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content,str):
        raise LLMProtocolError("message.content 必须是字符串或NULL")

    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls,list):
        raise LLMProtocolError("message.tool_calls 必须是数组")

    usage = payload.get("usage") or {}
    if not isinstance(usage,dict):
        raise LLMProtocolError("usage 必须是对象")
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        raw=payload
    )
