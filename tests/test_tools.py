import json
import tempfile
import unittest
from pathlib import Path

from mini_agent.tools.registry import ToolRegistry


class TestToolRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.registry = ToolRegistry(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def invoke(
        self, name: str, arguments: dict[str, object] | None = None
    ) -> dict[str, object]:
        return json.loads(self.registry.execute(name, arguments or {}))

    def test_unknown_tool(self) -> None:
        result = self.invoke("missing", {})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "TOOL_NOT_FOUND")

    def test_missing_required_argument(self) -> None:
        result = self.invoke("calculator", {})
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("expression", str(result["content"]))

    def test_wrong_argument_type(self) -> None:
        result = self.invoke("calculator", {"expression": 1})
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("expression", str(result["content"]))

    def test_unknown_argument_rejected(self) -> None:
        result = self.invoke(
            "calculator", {"expression": "1+1", "unexpected": True}
        )
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("unexpected", str(result["content"]))

    def test_out_of_range_argument(self) -> None:
        result = self.invoke(
            "read_file", {"path": "a.txt", "max_bytes": 0}
        )
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("max_bytes", str(result["content"]))

    def test_calculator(self) -> None:
        result = self.invoke("calculator", {"expression": "1 + 2 * 3"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["content"], "7")

    def test_calculator_float_format(self) -> None:
        result = self.invoke("calculator", {"expression": "0.1 + 0.2"})
        self.assertEqual(result["content"], "0.3")

    def test_calculator_rejects_function_call(self) -> None:
        result = self.invoke(
            "calculator", {"expression": "__import__('os').system('dir')"}
        )
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("Call", str(result["content"]))

    def test_calculator_rejects_large_exponent(self) -> None:
        result = self.invoke("calculator", {"expression": "2 ** 100"})
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("指数", str(result["content"]))

    def test_calculator_division_by_zero(self) -> None:
        result = self.invoke("calculator", {"expression": "1 / 0"})
        self.assertEqual(result["error_code"], "TOOL_EXECUTION_ERROR")
        self.assertIn("除数", str(result["content"]))

    def test_calculator_rejects_non_finite_result(self) -> None:
        result = self.invoke("calculator", {"expression": "1e308 * 10"})
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("有限", str(result["content"]))

    def test_calculator_rejects_infinite_literal(self) -> None:
        result = self.invoke("calculator", {"expression": "1e309"})
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("有限", str(result["content"]))

    def test_write_and_read_file(self) -> None:
        written = self.invoke(
            "write_file", {"path": "notes/a.txt", "content": "hello"}
        )
        self.assertEqual(written["status"], "success")
        self.assertTrue((self.root / "notes" / "a.txt").is_file())

        read = self.invoke("read_file", {"path": "notes/a.txt"})
        self.assertEqual(read["status"], "success")
        self.assertEqual(read["content"], "hello")

    def test_write_refuses_overwrite_by_default(self) -> None:
        self.invoke("write_file", {"path": "a.txt", "content": "one"})
        result = self.invoke("write_file", {"path": "a.txt", "content": "two"})
        self.assertEqual(result["error_code"], "PERMISSION_DENIED")
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "one")

    def test_write_allows_explicit_overwrite(self) -> None:
        self.invoke("write_file", {"path": "a.txt", "content": "one"})
        result = self.invoke(
            "write_file",
            {"path": "a.txt", "content": "two", "overwrite": True},
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual((self.root / "a.txt").read_text(encoding="utf-8"), "two")

    def test_read_missing_file(self) -> None:
        result = self.invoke("read_file", {"path": "missing.txt"})
        self.assertEqual(result["error_code"], "TOOL_EXECUTION_ERROR")
        self.assertIn("不存在", str(result["content"]))

    def test_read_directory_rejected(self) -> None:
        (self.root / "folder").mkdir()
        result = self.invoke("read_file", {"path": "folder"})
        self.assertEqual(result["error_code"], "TOOL_EXECUTION_ERROR")

    def test_list_dir(self) -> None:
        (self.root / "b.txt").write_text("b", encoding="utf-8")
        (self.root / "a.txt").write_text("a", encoding="utf-8")
        (self.root / "sub").mkdir()
        result = self.invoke("list_dir", {})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["content"], "sub/\na.txt\nb.txt")

    def test_list_empty_dir(self) -> None:
        (self.root / "empty").mkdir()
        result = self.invoke("list_dir", {"path": "empty"})
        self.assertEqual(result["content"], "（空目录）")

    def test_analyze_csv_statistics(self) -> None:
        (self.root / "sales.csv").write_text(
            "name,sales\nA,1200\nB,980\nC,760\n", encoding="utf-8"
        )
        result = self.invoke("analyze_csv", {"path": "sales.csv"})
        self.assertEqual(result["status"], "success")
        content = str(result["content"])
        self.assertIn("行数：3", content)
        self.assertIn("sales: min=760, max=1200", content)

    def test_analyze_csv_sort(self) -> None:
        (self.root / "sales.csv").write_text(
            "name,sales\nA,1200\nB,980\nC,760\n", encoding="utf-8"
        )
        result = self.invoke(
            "analyze_csv",
            {"path": "sales.csv", "sort_by": "sales", "limit": 2},
        )
        content = str(result["content"])
        self.assertIn("按 sales 降序 Top 2", content)
        self.assertIn("name=A | sales=1200", content)
        self.assertIn("name=B | sales=980", content)

    def test_analyze_csv_unknown_sort_column(self) -> None:
        (self.root / "sales.csv").write_text(
            "name,sales\nA,1\n", encoding="utf-8"
        )
        result = self.invoke(
            "analyze_csv", {"path": "sales.csv", "sort_by": "missing"}
        )
        self.assertEqual(result["error_code"], "INVALID_ARGUMENTS")
        self.assertIn("sort_by", str(result["content"]))

    def test_output_is_truncated(self) -> None:
        registry = ToolRegistry(self.root, max_output_chars=20)
        registry.execute("write_file", {"path": "long.txt", "content": "x" * 100})
        result = json.loads(registry.execute("read_file", {"path": "long.txt"}))
        content = str(result["content"])
        self.assertLessEqual(len(content), 20)
        self.assertTrue(content.endswith("[truncated]"))

    def test_describe_contains_tool_schema(self) -> None:
        description = self.registry.describe()
        for name in ("calculator", "read_file", "write_file", "list_dir", "analyze_csv"):
            self.assertIn(name, description)
        self.assertIn("参数 schema", description)

    def test_result_has_duration(self) -> None:
        result = self.invoke("calculator", {"expression": "1+1"})
        self.assertIsInstance(result["duration_ms"], int)
        self.assertGreaterEqual(int(result["duration_ms"]), 0)

    def test_loop_uses_registry(self) -> None:
        from mini_agent.agent.loop import AgentLoop, LoopStatus, RunLimits
        from mini_agent.llm.mock import MockLLMClient
        from mini_agent.llm.protocol import LLMResponse

        call = {
            "action": "tool_call",
            "thought": "calculate",
            "tool": "calculator",
            "arguments": {"expression": "1+1"},
        }
        final = {"action": "final", "thought": "done", "content": "2"}
        client = MockLLMClient(
            [
                LLMResponse(content=json.dumps(call)),
                LLMResponse(content=json.dumps(final)),
            ]
        )
        result = AgentLoop(client, self.registry, RunLimits()).run("1+1")

        self.assertIs(result.status, LoopStatus.DONE)
        self.assertEqual(result.answer, "2")
        observation = json.loads(result.messages[3]["content"])
        self.assertEqual(observation["status"], "success")
        self.assertEqual(observation["content"], "2")


if __name__ == "__main__":
    unittest.main()