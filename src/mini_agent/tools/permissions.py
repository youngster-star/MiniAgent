"""工作区路径解析：所有文件工具必须先经过这里"""

from __future__ import annotations

from pathlib import Path

from mini_agent.tools.base import ToolError

def resolve_workspace_path(workspace: Path, raw: str,*,must_exist:bool = False) -> Path:
    """把相对路径解析到工作区，并阻止绝对路径与 ../ 越界"""
    if not raw or not raw.strip():
        raise ToolError("INVALID_ARGUMENTS", "path 不能为空")

    candidate = Path(raw)
    if candidate.is_absolute():
        raise ToolError("PERMISSION_DENIED", "不允许使用绝对路径")

    root = workspace.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ToolError("PERMISSION_DENIED", f"路径越界：{raw}") from exc

    if must_exist and not resolved.exists():
        raise ToolError("TOOL_EXECUTION_ERROR", f"路径不存在：{raw}")
    return resolved