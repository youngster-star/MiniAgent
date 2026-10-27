"""
配置加载：默认连接本地 Ollama，缺失或非法时快速失败
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"

class ConfigError(ValueError):
    """配置缺失或格式错误"""

@dataclass(frozen=True)
class Config:
    """不可变运行配置"""
    model:str                           # 模型名称
    base_url:str = OLLAMA_BASE_URL      # 默认模型地址
    api_key:str = ""                    # 密钥
    timeout:float = 120.0               # 超时时间
    max_retries:int = 2                 # 最大重试次数
    retry_base_delay:float = 0.5        # 重试基础延迟
    reasoning_effort:str = "none"       # 默认关闭思考模型的推理输出

    def __repr__(self) -> str:          # __repr__ : 表示对象的字符串，类似于Java的toString()
        # 覆盖 dataclass 自动生成的 __repr__，避免密钥进入日志
        return (
            f"Config(base_url={self.base_url!r},model={self.model!r},"
            f"timeout={self.timeout!r},max_retries={self.max_retries!r},"
            "api_key='***')"
        )

def _read_float(values:Mapping[str,str],name:str,default:float) -> float:
    raw = values.get(name,"").strip()   # strip: 作用是去掉字符串首尾的空白字符
    if not raw:                         # 如果为空，返回默认值
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字，当前值：{raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} 必须大于 0，当前值：{raw!r}")
    return value

def _read_int(values:Mapping[str,str],name:str,default:int) -> int:
    raw = values.get(name,"").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数，当前值：{raw!r}") from exc
    if value < 0:
        raise ConfigError(f"{name}不能为负数，当前值：{raw!r}")
    return value

def load_config(env: Mapping[str,str] | None = None) -> Config:
    """加载配置： env 参数用于测试注入"""
    values = os.environ if env is None else env
    model = values.get("MINIAGENT_MODEL","").strip()
    if not model:
        raise ConfigError("缺少环境变量 MINIAGENT_MODEL; 先执行 ollama list 查看本地模型名")
    base_url = values.get("MINIAGENT_BASE_URL","").strip().rstrip("/")
    base_url = base_url or OLLAMA_BASE_URL
    api_key = values.get("MINIAGENT_API_KEY","").strip()

    return Config(
        model=model,
        base_url=base_url,
        api_key=api_key,
        timeout=_read_float(values,"MINIAGENT_TIMEOUT",120.0),
        max_retries=_read_int(values,"MINIAGENT_MAX_RETRIES",2),
        retry_base_delay=_read_float(values,"MINIAGENT_RETRY_BASE_DELAY",0.5),
        reasoning_effort=values.get("MINIAGENT_REASONING_EFFORT","none").strip(),
    )