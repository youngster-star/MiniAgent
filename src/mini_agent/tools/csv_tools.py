"""analyze_csv：读取 CSV，输出列信息、数值统计与排序结果"""

from __future__ import annotations

import csv
from typing import Any

from mini_agent.tools.base import ToolContext, ToolError
from mini_agent.tools.permissions import resolve_workspace_path


def analyze_csv(context: ToolContext, arguments: dict[str, Any]) -> str:
    path = resolve_workspace_path(
        context.workspace, arguments["path"], must_exist=True
    )
    if not path.is_file():
        raise ToolError("TOOL_EXECUTION_ERROR", f"不是文件：{arguments['path']}")

    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ToolError("TOOL_EXECUTION_ERROR", f"读取 CSV 失败：{exc}") from exc

    if not columns:
        raise ToolError("TOOL_EXECUTION_ERROR", "CSV 缺少表头")
    if not rows:
        raise ToolError("TOOL_EXECUTION_ERROR", "CSV 没有数据行")

    sort_by = arguments.get("sort_by")
    if sort_by and sort_by not in columns:
        raise ToolError("INVALID_ARGUMENTS", f"sort_by 不存在：{sort_by}")

    limit = int(arguments.get("limit", 5))
    numeric_columns = _numeric_columns(columns, rows)
    lines = [f"行数：{len(rows)}", f"列：{', '.join(columns)}"]

    if numeric_columns:
        lines.append("数值列统计：")
        for name, values in numeric_columns.items():
            average = sum(values) / len(values)
            lines.append(
                f"- {name}: min={_format(min(values))}, "
                f"max={_format(max(values))}, avg={_format(average)}"
            )

    if sort_by:
        ordered = sorted(rows, key=lambda row: _sort_key(row, sort_by), reverse=True)
        lines.append(f"按 {sort_by} 降序 Top {min(limit, len(ordered))}：")
    else:
        ordered = rows
        lines.append(f"前 {min(limit, len(ordered))} 行：")

    for row in ordered[:limit]:
        lines.append(
            " | ".join(f"{name}={row.get(name, '')}" for name in columns)
        )
    return "\n".join(lines)


def _numeric_columns(
    columns: list[str], rows: list[dict[str, str]]
) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for name in columns:
        values: list[float] = []
        for row in rows:
            try:
                values.append(float(row.get(name, "")))
            except ValueError:
                break
        else:
            result[name] = values
    return result


def _sort_key(row: dict[str, str], column: str) -> tuple[int, float | str]:
    raw = row.get(column, "")
    try:
        return (0, float(raw))
    except ValueError:
        return (1, raw)


def _format(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")