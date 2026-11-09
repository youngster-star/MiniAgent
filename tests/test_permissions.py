import json
import tempfile
import unittest
from pathlib import Path

from mini_agent.tools.registry import ToolRegistry


class TestToolPermissions(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.workspace = self.base / "workspace"
        self.registry = ToolRegistry(self.workspace)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def invoke(
        self, name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        return json.loads(self.registry.execute(name, arguments))

    def test_parent_traversal_rejected(self) -> None:
        (self.base / "outside.txt").write_text("secret", encoding="utf-8")
        result = self.invoke("read_file", {"path": "../outside.txt"})
        self.assertEqual(result["error_code"], "PERMISSION_DENIED")
        self.assertNotIn("secret", str(result["content"]))

    def test_absolute_path_rejected(self) -> None:
        target = self.base / "outside.txt"
        target.write_text("secret", encoding="utf-8")
        result = self.invoke("read_file", {"path": str(target)})
        self.assertEqual(result["error_code"], "PERMISSION_DENIED")

    def test_write_parent_traversal_rejected(self) -> None:
        result = self.invoke(
            "write_file", {"path": "../escape.txt", "content": "x"}
        )
        self.assertEqual(result["error_code"], "PERMISSION_DENIED")
        self.assertFalse((self.base / "escape.txt").exists())

    def test_list_parent_traversal_rejected(self) -> None:
        result = self.invoke("list_dir", {"path": ".."})
        self.assertEqual(result["error_code"], "PERMISSION_DENIED")

    def test_nested_path_inside_workspace_allowed(self) -> None:
        result = self.invoke(
            "write_file", {"path": "a/b/c.txt", "content": "ok"}
        )
        self.assertEqual(result["status"], "success")
        read = self.invoke("read_file", {"path": "a/b/c.txt"})
        self.assertEqual(read["content"], "ok")

    def test_missing_path_does_not_create_file(self) -> None:
        result = self.invoke("read_file", {"path": "a/b.txt"})
        self.assertEqual(result["error_code"], "TOOL_EXECUTION_ERROR")
        self.assertFalse((self.workspace / "a").exists())

    def test_relative_dot_stays_inside(self) -> None:
        (self.workspace / "a.txt").write_text("ok", encoding="utf-8")
        result = self.invoke("read_file", {"path": "./a.txt"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["content"], "ok")


if __name__ == "__main__":
    unittest.main()