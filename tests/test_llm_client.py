import json
import socket
import unittest

from mini_agent.config import Config
from mini_agent.llm.client import (
    HttpLLMClient,
    LLMHTTPError,
    LLMTimeoutError,
)
from mini_agent.llm.protocol import LLMProtocolError


def make_config(**overrides: object) -> Config:
    values: dict[str, object] = {
        "api_key": "sk-secret",
        "base_url": "https://api.example.com/v1",
        "model": "demo",
        "timeout": 1.0,
        "max_retries": 0,
        "retry_base_delay": 0.0,
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


def success_body(content: str = "ok") -> bytes:
    payload = {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"total_tokens": 3},
    }
    return json.dumps(payload).encode("utf-8")


class ScriptedTransport:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        self.calls.append(
            {"url": url, "headers": headers, "body": body, "timeout": timeout}
        )
        if not self._outcomes:
            raise AssertionError("传输脚本已用尽")
        item = self._outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[return-value]


class TestHttpLLMClient(unittest.TestCase):
    def test_success(self) -> None:
        transport = ScriptedTransport([(200, success_body("hello"))])
        client = HttpLLMClient(make_config(), transport=transport)
        response = client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(response.content, "hello")
        self.assertEqual(response.usage["total_tokens"], 3)
        self.assertEqual(len(transport.calls), 1)

    def test_request_shape(self) -> None:
        transport = ScriptedTransport([(200, success_body())])
        client = HttpLLMClient(make_config(), transport=transport)
        client.chat([{"role": "user", "content": "hi"}])
        call = transport.calls[0]
        self.assertTrue(str(call["url"]).endswith("/chat/completions"))
        headers = call["headers"]
        self.assertEqual(headers["Authorization"], "Bearer sk-secret")
        body = json.loads(bytes(call["body"]).decode("utf-8"))
        self.assertEqual(body["model"], "demo")
        self.assertEqual(body["temperature"], 0)
        self.assertFalse(body["stream"])
        self.assertEqual(body["reasoning_effort"], "none")

    def test_ollama_request_without_api_key(self) -> None:
        transport = ScriptedTransport([(200, success_body())])
        config = make_config(
            api_key="",
            base_url="http://127.0.0.1:11434/v1",
        )
        client = HttpLLMClient(config, transport=transport)
        client.chat([{"role": "user", "content": "hi"}])
        call = transport.calls[0]
        self.assertEqual(
            call["url"], "http://127.0.0.1:11434/v1/chat/completions"
        )
        headers = call["headers"]
        self.assertNotIn("Authorization", headers)

    def test_reasoning_effort_auto_is_omitted(self) -> None:
        transport = ScriptedTransport([(200, success_body())])
        config = make_config(reasoning_effort="auto")
        client = HttpLLMClient(config, transport=transport)
        client.chat([{"role": "user", "content": "hi"}])
        body = json.loads(bytes(transport.calls[0]["body"]).decode("utf-8"))
        self.assertNotIn("reasoning_effort", body)

    def test_retry_on_500_then_success(self) -> None:
        transport = ScriptedTransport([(500, b"oops"), (200, success_body("ok"))])
        config = make_config(max_retries=1)
        client = HttpLLMClient(config, transport=transport)
        response = client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(response.content, "ok")
        self.assertEqual(len(transport.calls), 2)

    def test_no_retry_on_401(self) -> None:
        transport = ScriptedTransport([(401, b"unauthorized")])
        config = make_config(max_retries=3)
        client = HttpLLMClient(config, transport=transport)
        with self.assertRaises(LLMHTTPError) as ctx:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(len(transport.calls), 1)

    def test_timeout_raises(self) -> None:
        transport = ScriptedTransport([socket.timeout("timeout")])
        client = HttpLLMClient(make_config(), transport=transport)
        with self.assertRaises(LLMTimeoutError):
            client.chat([{"role": "user", "content": "hi"}])

    def test_invalid_json_raises_protocol_error(self) -> None:
        transport = ScriptedTransport([(200, b"not-json")])
        client = HttpLLMClient(make_config(), transport=transport)
        with self.assertRaises(LLMProtocolError):
            client.chat([{"role": "user", "content": "hi"}])

    def test_missing_choices_raises_protocol_error(self) -> None:
        transport = ScriptedTransport([(200, b'{"usage": {}}')])
        client = HttpLLMClient(make_config(), transport=transport)
        with self.assertRaises(LLMProtocolError):
            client.chat([{"role": "user", "content": "hi"}])

    def test_exception_message_has_no_api_key(self) -> None:
        transport = ScriptedTransport([(500, b"error")])
        client = HttpLLMClient(make_config(), transport=transport)
        with self.assertRaises(LLMHTTPError) as ctx:
            client.chat([{"role": "user", "content": "hi"}])
        self.assertNotIn("sk-secret", str(ctx.exception))

    def test_empty_messages_rejected(self) -> None:
        client = HttpLLMClient(make_config(), transport=ScriptedTransport([]))
        with self.assertRaises(ValueError):
            client.chat([])


if __name__ == "__main__":
    unittest.main()