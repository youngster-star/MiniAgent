import json
import unittest

from mini_agent.agent.decision import ActionType, parse_decision


def raw(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


class TestParseDecision(unittest.TestCase):
    def test_final(self) -> None:
        decision = parse_decision(
            raw({"action": "final", "thought": "完成", "content": "答案"})
        )
        self.assertIs(decision.type, ActionType.FINAL)
        self.assertEqual(decision.content, "答案")
        self.assertEqual(decision.thought, "完成")
        self.assertEqual(decision.error, "")

    def test_tool_call(self) -> None:
        decision = parse_decision(
            raw(
                {
                    "action": "tool_call",
                    "thought": "需要计算",
                    "tool": "calculator",
                    "arguments": {"expression": "1+1"},
                }
            )
        )
        self.assertIs(decision.type, ActionType.TOOL_CALL)
        self.assertEqual(decision.tool, "calculator")
        self.assertEqual(decision.arguments, {"expression": "1+1"})

    def test_json_code_fence_is_stripped(self) -> None:
        text = '```json\n{"action":"final","content":"ok"}\n```'
        decision = parse_decision(text)
        self.assertIs(decision.type, ActionType.FINAL)
        self.assertEqual(decision.content, "ok")

    def test_invalid_json(self) -> None:
        decision = parse_decision("{not json")
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("不是合法 JSON", decision.error)
        self.assertEqual(decision.raw, "{not json")

    def test_root_must_be_object(self) -> None:
        decision = parse_decision("[]")
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("根节点", decision.error)

    def test_missing_action(self) -> None:
        decision = parse_decision(raw({"content": "ok"}))
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("action", decision.error)

    def test_unknown_action(self) -> None:
        decision = parse_decision(raw({"action": "plan"}))
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("未知 action", decision.error)

    def test_invalid_action_is_rejected(self) -> None:
        decision = parse_decision(raw({"action": "invalid"}))
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("不能是 invalid", decision.error)

    def test_final_requires_non_empty_content(self) -> None:
        decision = parse_decision(raw({"action": "final", "content": "  "}))
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("content", decision.error)

    def test_content_must_be_string(self) -> None:
        decision = parse_decision(raw({"action": "final", "content": 1}))
        self.assertIs(decision.type, ActionType.INVALID)

    def test_thought_must_be_string(self) -> None:
        decision = parse_decision(
            raw({"action": "final", "thought": [], "content": "ok"})
        )
        self.assertIs(decision.type, ActionType.INVALID)

    def test_tool_call_requires_tool_name(self) -> None:
        decision = parse_decision(raw({"action": "tool_call", "tool": ""}))
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("tool", decision.error)

    def test_arguments_must_be_object(self) -> None:
        decision = parse_decision(
            raw({"action": "tool_call", "tool": "x", "arguments": []})
        )
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("arguments", decision.error)

    def test_arguments_default_to_empty_dict(self) -> None:
        decision = parse_decision(raw({"action": "tool_call", "tool": "x"}))
        self.assertIs(decision.type, ActionType.TOOL_CALL)
        self.assertEqual(decision.arguments, {})

    def test_empty_output(self) -> None:
        decision = parse_decision("   ")
        self.assertIs(decision.type, ActionType.INVALID)
        self.assertIn("为空", decision.error)

    def test_raw_is_preserved(self) -> None:
        text = '{"action":"final","content":"ok"}'
        self.assertEqual(parse_decision(text).raw, text)


if __name__ == "__main__":
    unittest.main()