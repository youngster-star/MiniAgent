"""测试用 Mock 客户端：按脚本返回预置响应"""

from __future__ import annotations

from typing import Any

from mini_agent.llm.protocol import LLMResponse

class MockLLMClient:
    def __init__(self,script: list[LLMResponse | Exception]) -> None:
        self._script = script
        self.calls: list[dict[str, Any]] = []

    def chat(self,messages:list[dict[str,Any]],
             tools: list[dict[str,Any]] | None = None) -> LLMResponse:
        self.calls.append({"messages":list(messages),"tools":tools})
        if not self._script:
            raise AssertionError("Mock 响应已用尽，请检查测试脚本")
        item = self._script.pop(0)
        if isinstance(item,Exception):
            raise item
        return item