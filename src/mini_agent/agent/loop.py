"""有界 Agent Loop：请求模型、解析决策、执行或结束"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from mini_agent.agent.decision import parse_decision, ActionType
from mini_agent.llm.client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个受控 Agent 运行时中的决策器。
你只能输出一个 JSON 对象，不要输出 Markdown 代码块，不要输出解释性文字。
可用动作：
1. {"action":"final","thought":"...","content":"给用户的最终答案"}
2. {"action":"tool_call","thought":"...","tool":"工具名","arguments":{...}}
规则：
- 任务完成或无需工具时，使用 final。
- 需要外部信息或操作时，使用 tool_call；一次只请求一个工具。
- 只能使用工具清单中列出的工具，不要编造工具名。
- 不要编造工具结果。
- 工具失败时阅读 error_code，调整参数或改用 final，不要重复相同调用。
"""
class LoopStatus(str,Enum):
    """循环的终止状态"""

    DONE = "done"
    MAX_STEPS = "max_steps"
    INVALID_LIMIT = "invalid_limit"
    DUPLICATE_LIMIT = "duplicate_limit"

@dataclass(frozen=True)
class RunLimits:
    """单词运行的硬限制"""

    max_steps:int = 10
    max_consecutive_invalid:int = 3
    max_duplicate_calls:int = 3

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError("max_steps 必须大于 0")
        if self.max_consecutive_invalid <= 0:
            raise ValueError("max_consecutive_invalid 必须大于 0")
        if self.max_duplicate_calls <= 0:
            raise ValueError("max_duplicate_calls 必须大于 0")

@dataclass(frozen=True)
class LoopResult:
    """循环结果：正常结束和受限终止都通过 status 区分"""

    status: LoopStatus
    answer: str
    steps: int
    messages: list[dict[str,Any]] = field(default_factory=list)
    error_code: str | None = None

class ToolExecutor(Protocol):
    """阶段二只依赖这个文件，阶段三用真实注册表实现"""

    def execute(self,name:str,arguments:dict[str,Any]) -> str:
        ...

class UnavailableToolExecutor:
    """阶段二没有工具，返回结构化错误，让循环继续"""

    def execute(self,name:str,arguments:dict[str,Any]) -> str:
        return json.dumps(
            {
                "tool":name,
                "status":"error",
                "error_code":"TOOL_NOT_FOUND",
                "content":f"阶段二未注册工具{name!r}，请根据已有信息直接给出 final 。"
            },
            ensure_ascii=False,
        )

def _invalid_prompt(error: str) -> str:
    return (
        f"上一条输出不符合协议：{error}\n"
        "只输出一个 JSON 对象，不要 Markdown 代码块。\n"
        'final 格式：{"action":"final","thought":"...","content":"..."}\n'
        'tool_call 格式：{"action":"tool_call","thought":"...","tool":"...","arguments":{...}}'
    )

def _duplicate_prompt(tool:str,limit:int) -> str:
    return (
        f"工具 {tool!r} 以相同参数被重复调用超过 {limit} 次。"
        "请停止重复调用，基于已有观察直接使用 final，或明确说明无法完成。"
    )

def _fingerprint(tool:str,arguments:dict[str,Any]) -> str:
    canonical = json.dumps(
        {"tool":tool,"arguments":arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",",":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

class AgentLoop:
    """单次任务的有界决策循环"""

    def __init__(
            self,
            client: LLMClient,
            executor: ToolExecutor,
            limits: RunLimits,
            system_prompt:str = SYSTEM_PROMPT
    ) -> None:
        self._client = client
        self._limits = limits
        self._system_prompt = system_prompt
        self._executor = executor
    def run(self,goal:str) -> LoopResult:
        if not goal.strip():
            raise ValueError("goal 不能为空")

        messages: list[dict[str,Any]] = [
            {"role":"system","content":self._system_prompt},
            {"role":"user","content":goal},
        ]
        invalid_streak = 0
        call_counts: dict[str,int] = {}

        for step in range(1,self._limits.max_steps + 1):
            logger.info("step %d/%d",step,self._limits.max_steps)
            response = self._client.chat(messages)
            decision = parse_decision(response.content)
            logger.info("decision type=%s",decision.type.value)
            messages.append({"role": "assistant", "content": decision.raw})

            if decision.type is ActionType.FINAL:
                return LoopResult(
                    status=LoopStatus.DONE,
                    answer=decision.content,
                    steps=step,
                    messages=messages
                )

            if decision.type is ActionType.INVALID:
                invalid_streak += 1
                logger.warning(
                    "invalid decision (%d/%d): %s",
                    invalid_streak,
                    self._limits.max_consecutive_invalid,
                    decision.error,
                )
                messages.append(
                    {"role": "user", "content": _invalid_prompt(decision.error)}
                )
                if invalid_streak >= self._limits.max_consecutive_invalid:
                    return LoopResult(
                        status=LoopStatus.INVALID_LIMIT,
                        answer="",
                        steps=step,
                        messages=messages,
                        error_code="INVALID_DECISION",
                    )
                continue

            invalid_streak = 0
            tool = decision.tool or ""
            fingerprint = _fingerprint(tool,decision.arguments)
            count = call_counts.get(fingerprint,0) + 1
            call_counts[fingerprint] = count

            if count > self._limits.max_duplicate_calls:
                messages.append(
                    {
                        "role": "user",
                        "content": _duplicate_prompt(
                            tool, self._limits.max_duplicate_calls
                        ),
                    }
                )
                return LoopResult(
                    status=LoopStatus.DUPLICATE_LIMIT,
                    answer="",
                    steps=step,
                    messages=messages,
                    error_code="DUPLICATE_TOOL_CALL",
                )
            observation = self._executor.execute(tool,decision.arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"call-{step}",
                    "name": tool,
                    "content": observation,
                }
            )
        return LoopResult(
            status=LoopStatus.MAX_STEPS,
            answer="",
            steps=self._limits.max_steps,
            messages=messages,
            error_code="MAX_STEPS_EXCEEDED",
        )