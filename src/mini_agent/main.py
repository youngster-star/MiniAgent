"""阶段二入口：有界 Agent Loop"""

from __future__ import annotations

import argparse         # 解析命令行参数
import logging
import sys
from dataclasses import replace

from mini_agent.agent.loop import AgentLoop, UnavailableToolExecutor, RunLimits, LoopStatus
from mini_agent.config import Config, ConfigError, load_config
from mini_agent.llm.client import HttpLLMClient, LLMError
from mini_agent.llm.protocol import LLMProtocolError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MiniAgent 阶段一 CLI")
    parser.add_argument("message", nargs="?", help="单次任务内容")
    parser.add_argument("--model", help="覆盖 MINIAGENT_MODEL")
    parser.add_argument("--base-url", help="覆盖 MINIAGENT_BASE_URL")
    parser.add_argument("--timeout", type=float, help="覆盖单次请求超时（秒）")
    parser.add_argument("--max-steps", type=int, help="覆盖最大决策步数")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    config = load_config()
    updates: dict[str, object] = {}
    if args.model:
        updates["model"] = args.model
    if args.base_url:
        updates["base_url"] = args.base_url.rstrip("/")
    if args.timeout is not None:
        if args.timeout <= 0:
            raise ConfigError("--timeout 必须大于 0")
        updates["timeout"] = args.timeout
    if args.max_steps is not None:
        if args.max_steps <= 0:
            raise ConfigError("--max-steps 必须大于 0")
        updates["max_steps"] = args.max_steps
    if not updates:
        return config
    return replace(config, **updates)


def run_once(client: HttpLLMClient, goal: str, config: Config) -> int:
    loop = AgentLoop(
        client=client,
        executor=UnavailableToolExecutor(),
        limits=RunLimits(
            max_steps=config.max_steps,
            max_consecutive_invalid=config.max_consecutive_invalid,
            max_duplicate_calls=config.max_duplicate_calls,
        ),
    )
    try:
        result = loop.run(goal)
    except LLMProtocolError as exc:
        print(f"协议错误：{exc}", file=sys.stderr)
        return 1
    except LLMError as exc:
        print(f"模型调用失败[{exc.code}]：{exc}", file=sys.stderr)
        return 1

    if result.status is LoopStatus.DONE:
        print(result.answer)
        return 0

    print(
        f"运行终止[{result.error_code}]：{result.status.value}，step={result.steps}",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        config = config_from_args(args)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    if not args.message:
        parser.print_help()
        return 2

    client = HttpLLMClient(config)
    return run_once(client, args.message, config)


if __name__ == "__main__":
    raise SystemExit(main())