"""文件工具：read_file、write_file、list_dir"""

from __future__ import annotations

from typing import Any

from mini_agent.tools.base import ToolContext, ToolError
from mini_agent.tools.permissions import resolve_workspace_path


def read_file(context: ToolContext, arguments: dict[str, Any]) -> str:
    path = resolve_workspace_path(
        context.workspace, arguments["path"], must_exist=True
    )
    if not path.is_file():
        raise ToolError("TOOL_EXECUTION_ERROR", f"不是文件：{arguments['path']}")

    max_bytes = min(
        int(arguments.get("max_bytes", 20000)), context.max_output_chars
    )
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    if truncated:
        text += "\n...[truncated]"
    return text


def write_file(context: ToolContext, arguments: dict[str, Any]) -> str:
    path = resolve_workspace_path(context.workspace, arguments["path"])
    if path.exists():
        if path.is_dir():
            raise ToolError("TOOL_EXECUTION_ERROR", "目标路径是目录")
        if not arguments.get("overwrite", False):
            raise ToolError(
                "PERMISSION_DENIED",
                "文件已存在；覆盖需要显式传入 overwrite=true",
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    content = arguments["content"]
    path.write_text(content, encoding="utf-8")
    relative = path.relative_to(context.workspace).as_posix()
    return f"已写入 {relative}（{len(content)} 字符）"


def list_dir(context: ToolContext, arguments: dict[str, Any]) -> str:
    path = resolve_workspace_path(
        context.workspace, arguments.get("path", "."), must_exist=True
    )
    if not path.is_dir():
        raise ToolError("TOOL_EXECUTION_ERROR", f"不是目录：{arguments.get('path', '.')}")

    entries = sorted(
        path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())
    )
    lines = [
        f"{item.name}/" if item.is_dir() else item.name
        for item in entries[:200]
    ]
    if len(entries) > 200:
        lines.append(f"... 还有 {len(entries) - 200} 项")
    return "\n".join(lines) or "（空目录）"