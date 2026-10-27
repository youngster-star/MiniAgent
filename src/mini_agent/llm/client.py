"""HTTP 客户端：请求构造、超时、重试、错误归一化"""

from __future__ import annotations

import json
import logging
import random
import socket
import time
import urllib.error
import urllib.request
from typing import Any,Callable,Protocol

from mini_agent.config import Config
from mini_agent.llm.protocol import LLMProtocolError,LLMResponse,parse_chat_completion

logger = logging.getLogger(__name__)

# (url, headers, body, timeout) -> (status, raw_body)
Transport = Callable[[str,dict[str,str],bytes,float],tuple[int,bytes]]

class LLMError(Exception):
    """所有模型调用错误的基类"""

    def __init__(self,message:str,code:str) -> None:
        super().__init__(message)
        self.code = code

class LLMHTTPError(LLMError):
    def __init__(self,message:str,status:int,body:str = "") -> None:
        super().__init__(message,code="LLM_HTTP_ERROR")
        self.status = status
        self.body = body[:500]

class LLMTimeoutError(LLMError):
    def __init__(self,message:str) -> None:
        super().__init__(message,code="LLM_TIMEOUT")

class LLMNetworkError(LLMError):
    def __init__(self,message:str) -> None:
        super().__init__(message,code="LLM_NETWORK_ERROR")

class LLMClient(Protocol):
    """抽象接口：阶段二循环只依赖这个协议"""

    def chat(self,messages:list[dict[str,Any]],tools: list[dict[str,Any]] | None = None) -> LLMResponse:
        ...

def urlopen_transport(
        url:str,
        headers:dict[str,str],
        body:bytes,
        timeout:float
    ) -> tuple[int,bytes]:
    """默认传入实现 测试时可替换为假函数"""
    request = urllib.request.Request(url,data=body,headers=headers,method="POST")
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        try:
            data = exc.read()
        finally:
            exc.close()
        return exc.code, data

class HttpLLMClient:
    """基于 HTTP 的 LLM 客户端"""
    def __init__(self,config:Config,transport:Transport | None = None) -> None:
        self._config = config
        self._transport = transport or urlopen_transport

    def chat(self,
             messages: list[dict[str,Any]],
             tools: list[dict[str,Any]] | None = None) -> LLMResponse:
        if not messages:
            raise ValueError("messages 不能为空")
        url = f"{self._config.base_url}/chat/completions"
        body = self._build_body(messages,tools)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "mini-agent/0.1",
        }
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        last_error: LLMError | None = None
        attempts = self._config.max_retries + 1

        for attempt in range(attempts):
            try:
                status,raw = self._transport(
                    url,headers,body,self._config.timeout
                )
            except (TimeoutError,socket.timeout) as exc:
                last_error = LLMTimeoutError(
                    f"模型请求超时({self._config.timeout}秒)"
                )
                last_error.__cause__ = exc
            except urllib.error.URLError as exc:
                if isinstance(exc.reason,(TimeoutError,socket.timeout)):
                    last_error = LLMTimeoutError(
                        f"模型请求超时({self._config.timeout}秒)"
                    )
                else:
                    last_error = LLMNetworkError(f"网络错误：{exc.reason}")
                last_error.__cause__ = exc
            else:
                if status in (429,500,502,503,504):
                    last_error = LLMHTTPError(
                        f"模型服务暂不可用，HTTP {status}",
                        status=status,
                        body=raw.decode("utf-8",errors="replace")
                    )
                elif status >= 400:
                    raise LLMHTTPError(
                        f"模型请求失败，HTTP {status}",
                        status=status,
                        body=raw.decode("utf-8",errors="replace")
                    )
                else:
                    return self._decode(raw)

            if attempt >= attempts - 1:
                break
            delay = self._config.retry_base_delay * (2 ** attempt)
            delay += random.uniform(0,0.2)
            logger.warning(
                "LLM 调用失败 (%s),%.2f 秒后重试 (%d/%d)",
                last_error.code,
                delay,
                attempt + 1,
                self._config.max_retries
            )
            time.sleep(delay)
        assert last_error is not None
        raise last_error
    def _build_body(self,
                    messages:list[dict[str,Any]],
                    tools:list[dict[str,Any]] | None) -> bytes:
        payload: dict[str,Any] = {
            "model":self._config.model,
            "messages":messages,
            "temperature":0,
            "stream":False,
        }
        effort = self._config.reasoning_effort
        if effort and effort != "auto":
            payload["reasoning_effort"] = effort # 关闭思考模型的长推理，避免 content 为空
        if tools:
            # ollama 的 OpenAI 兼容端点不支持 tool_choice
            # OpenAI 默认行为就是 auto 因此省略即可
            payload["tools"] = tools
        return json.dumps(payload,ensure_ascii=False).encode("utf-8")

    def _decode(self,raw:bytes) -> LLMResponse:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:
            raise LLMProtocolError("模型响应不是合法 JSON") from exc
        return  parse_chat_completion(payload)