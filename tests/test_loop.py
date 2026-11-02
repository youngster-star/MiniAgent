import json
import unittest
from typing import Any

from mini_agent.agent.loop import (
    AgentLoop,
    LoopStatus,
    RunLimits,
    UnavailableToolExecutor,
)
from mini_agent.llm.client import LLMHTTPError
from mini_agent.llm.mock import MockLLMClient
from mini_agent.llm.protocol import LLMResponse


def response(payload: object) -> LLMResponse:
    return LLMResponse(content=json.dumps(payload, ensure_ascii=False))


def final(content: str = "done") -> LLMResponse:
    return response({"action": "final", "thought": "ok", "content": content})


def tool_call(
    tool: str = "calculator", arguments: dict[str, Any] | None = None
) -> LLMResponse:
    return response(
        {
            "action": "tool_call",
            "thought": "call",
            "tool": tool,
            "arguments": {} if arguments is None else arguments,
        }
    )


class RecordingExecutor:
    def __init__(self, observation: str = "observation") -> None:
        self.observation = observation
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, arguments))
        return self.observation


class TestAgentLoop(unittest.TestCase):
    def test_final_ends_immediately(self) -> None:
        client = MockLLMClient([final("hello")])
        executor = RecordingExecutor()
        loop = AgentLoop(client, executor, RunLimits())

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.DONE)
        self.assertEqual(result.answer, "hello")
        self.assertEqual(result.steps, 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(executor.calls, [])
        self.assertEqual(
            [message["role"] for message in result.messages],
            ["system", "user", "assistant"],
        )

    def test_invalid_then_final(self) -> None:
        client = MockLLMClient([LLMResponse(content="{bad"), final("fixed")])
        loop = AgentLoop(client, RecordingExecutor(), RunLimits())

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.DONE)
        self.assertEqual(result.answer, "fixed")
        self.assertEqual(result.steps, 2)
        self.assertEqual(len(client.calls), 2)
        correction = result.messages[3]["content"]
        self.assertIn("不符合协议", correction)
        self.assertIn("不是合法 JSON", correction)

    def test_max_steps_terminates(self) -> None:
        client = MockLLMClient([tool_call(), tool_call()])
        executor = RecordingExecutor()
        loop = AgentLoop(
            client,
            executor,
            RunLimits(max_steps=2),
        )

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.MAX_STEPS)
        self.assertEqual(result.error_code, "MAX_STEPS_EXCEEDED")
        self.assertEqual(result.steps, 2)
        self.assertEqual(len(executor.calls), 2)

    def test_consecutive_invalid_limit(self) -> None:
        client = MockLLMClient(
            [LLMResponse(content="{bad"), LLMResponse(content="{bad2"), final()]
        )
        loop = AgentLoop(
            client,
            RecordingExecutor(),
            RunLimits(max_consecutive_invalid=2),
        )

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.INVALID_LIMIT)
        self.assertEqual(result.error_code, "INVALID_DECISION")
        self.assertEqual(result.steps, 2)
        self.assertEqual(len(client.calls), 2)

    def test_invalid_streak_resets_after_valid_decision(self) -> None:
        client = MockLLMClient(
            [
                LLMResponse(content="{bad"),
                tool_call(),
                LLMResponse(content="{bad2"),
                final("ok"),
            ]
        )
        loop = AgentLoop(
            client,
            RecordingExecutor(),
            RunLimits(max_consecutive_invalid=2),
        )

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.DONE)
        self.assertEqual(result.steps, 4)

    def test_tool_observation_is_appended(self) -> None:
        client = MockLLMClient(
            [tool_call("calculator", {"expression": "1+1"}), final("2")]
        )
        executor = RecordingExecutor("2")
        loop = AgentLoop(client, executor, RunLimits())

        result = loop.run("1+1")

        self.assertIs(result.status, LoopStatus.DONE)
        self.assertEqual(executor.calls, [("calculator", {"expression": "1+1"})])
        tool_message = result.messages[3]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["name"], "calculator")
        self.assertEqual(tool_message["content"], "2")
        self.assertEqual(tool_message["tool_call_id"], "call-1")

    def test_duplicate_tool_call_limit(self) -> None:
        client = MockLLMClient([tool_call() for _ in range(3)])
        executor = RecordingExecutor()
        loop = AgentLoop(
            client,
            executor,
            RunLimits(max_duplicate_calls=2),
        )

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.DUPLICATE_LIMIT)
        self.assertEqual(result.error_code, "DUPLICATE_TOOL_CALL")
        self.assertEqual(result.steps, 3)
        self.assertEqual(len(executor.calls), 2)

    def test_duplicate_fingerprint_ignores_key_order(self) -> None:
        client = MockLLMClient(
            [
                tool_call("calculator", {"a": 1, "b": 2}),
                tool_call("calculator", {"b": 2, "a": 1}),
            ]
        )
        executor = RecordingExecutor()
        loop = AgentLoop(
            client,
            executor,
            RunLimits(max_duplicate_calls=1),
        )

        result = loop.run("hi")

        self.assertIs(result.status, LoopStatus.DUPLICATE_LIMIT)
        self.assertEqual(len(executor.calls), 1)

    def test_llm_error_propagates(self) -> None:
        client = MockLLMClient([LLMHTTPError("boom", status=500)])
        executor = RecordingExecutor()
        loop = AgentLoop(client, executor, RunLimits())

        with self.assertRaises(LLMHTTPError):
            loop.run("hi")

        self.assertEqual(executor.calls, [])

    def test_empty_goal_rejected(self) -> None:
        loop = AgentLoop(MockLLMClient([]), RecordingExecutor(), RunLimits())
        with self.assertRaises(ValueError):
            loop.run("   ")

    def test_invalid_limits_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RunLimits(max_steps=0)
        with self.assertRaises(ValueError):
            RunLimits(max_consecutive_invalid=0)
        with self.assertRaises(ValueError):
            RunLimits(max_duplicate_calls=0)

    def test_unavailable_executor_returns_structured_error(self) -> None:
        observation = json.loads(
            UnavailableToolExecutor().execute("missing", {})
        )
        self.assertEqual(observation["status"], "error")
        self.assertEqual(observation["error_code"], "TOOL_NOT_FOUND")

    def test_assistant_raw_is_preserved(self) -> None:
        raw = json.dumps({"action": "final", "content": "ok"})
        client = MockLLMClient([LLMResponse(content=raw)])
        result = AgentLoop(client, RecordingExecutor(), RunLimits()).run("hi")
        self.assertEqual(result.messages[2]["content"], raw)


if __name__ == "__main__":
    unittest.main()