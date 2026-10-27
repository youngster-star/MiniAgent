# MiniAgent

一个从零实现的最小可用 Agent Runtime（智能体运行时）。

模型只负责理解、推理与决策；循环控制、工具调用、上下文管理、任务规划、错误处理与执行限额全部由本项目实现。不依赖 LangChain、LlamaIndex、AutoGen、CrewAI 等 Agent 框架。

## 项目状态

| 项目 | 状态 |
| --- | --- |
| 仓库初始化（uv + src 布局） | 完成 |
| PRD 与阶段设计文档 | 完成（本地保留，不纳入版本控制） |
| 阶段一：LLM Client | 完成 |
| 阶段二：Agent Loop | 待实现 |
| 阶段三：Tool Calling | 待实现 |
| 阶段四：Memory / Context | 待实现 |
| 阶段五：Planning | 待实现 |
| 阶段六：可靠性 / 评估 | 待实现 |

当前可运行：加载配置、调用本地 Ollama、解析响应并打印结果；支持超时、有限重试和类型化错误。

## 设计目标

- 单 Agent、多工具、多步执行，覆盖 ReAct 与 Plan-and-Execute。
- 运行时行为可解释、可复现、可测试。
- 零第三方运行期依赖，仅使用 Python 标准库。
- 安全边界由代码保证，而不是依赖模型自觉。

## 非目标

v1.0 不包含：多 Agent 协作、RAG / 向量数据库、Web UI、模型训练、分布式执行、容器级沙箱、生产级高可用。不实现本地推理引擎，本地模型通过 Ollama 作为外部服务接入。

## 架构

```text
CLI
 └─ Agent Loop
     ├─ Context Manager   （上下文构造、裁剪、摘要）
     ├─ Planner           （ReAct / Plan-and-Execute）
     ├─ LLM Client        （HTTP、协议解析、超时、重试）
     ├─ Memory            （会话历史、任务状态、持久化）
     ├─ Runtime           （权限、限额、执行编排）
     └─ Tool Registry     （注册、校验、分发、结果标准化）
```

数据流：用户任务 → 构建上下文 → 请求模型 → 解析决策 → 执行工具或结束 → 观察结果回灌 → 继续循环。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（推荐）或 Python 自带的 `venv`
- [Ollama](https://ollama.com/download)（默认模型服务，使用其 OpenAI 兼容端点）

## 快速开始

### 1. 安装 Ollama 并准备模型

```powershell
ollama pull qwen3.5:9b
ollama list
```

确认 Ollama 正在运行：

```powershell
ollama ps
curl.exe http://127.0.0.1:11434/api/tags
```

### 2. 安装 Python 环境

```powershell
uv python install 3.12
uv sync
```

不使用 uv 时，也可以用标准库创建虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

本项目运行期不依赖任何第三方包。

### 3. 配置环境变量

默认连接本机 Ollama，只需要指定模型名：

```powershell
$env:MINIAGENT_MODEL = "qwen3.5:9b"
```

macOS / Linux：

```bash
export MINIAGENT_MODEL="qwen3.5:9b"
```

只有连接远程 OpenAI 兼容服务时才需要设置地址和密钥：

```powershell
$env:MINIAGENT_BASE_URL = "https://api.example.com/v1"
$env:MINIAGENT_API_KEY = "sk-..."
$env:MINIAGENT_MODEL = "your-model-name"
```

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MINIAGENT_MODEL` | 无（必填） | 必须与 `ollama list` 中的名称一致 |
| `MINIAGENT_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama 的 OpenAI 兼容端点 |
| `MINIAGENT_API_KEY` | 空 | Ollama 不需要；远程服务才填 |
| `MINIAGENT_TIMEOUT` | `120` | 单次模型调用超时（秒） |
| `MINIAGENT_MAX_RETRIES` | `2` | 可重试错误的最大重试次数 |
| `MINIAGENT_REASONING_EFFORT` | `none` | 思考模型推理强度；`none` 关闭，`auto` 不发送该字段 |
| `MINIAGENT_MAX_STEPS` | `10` | Agent 最大步数 |
| `MINIAGENT_WORKSPACE` | `./workspace` | 文件工具允许操作的根目录 |
| `MINIAGENT_LOG_DIR` | `./logs` | 运行事件目录 |

> `MINIAGENT_MAX_STEPS`、`MINIAGENT_WORKSPACE`、`MINIAGENT_LOG_DIR` 随对应阶段实现逐步生效。

### 4. 运行

```powershell
uv run mini-agent "用一句话解释什么是幂等性"
```

只做配置检查、不调用模型：

```powershell
uv run mini-agent --help
```

### 5. 测试

```powershell
uv run python -m unittest discover -s tests -v
```

单元测试不访问网络；需要真实模型的端到端测试在 Ollama 不可用时自动跳过。

## 本地模型（Ollama）

- 使用 OpenAI 兼容端点 `http://127.0.0.1:11434/v1`，客户端只发送 `stream: false` 的普通请求。
- 模型名必须与 `ollama list` 完全一致，包含 `:tag`。
- 思考模型（qwen3、qwen3.5、deepseek-r1、gpt-oss 等）可能把 token 全用于推理并返回空 `content`。默认 `MINIAGENT_REASONING_EFFORT=none` 关闭推理；需要时改为 `low` / `medium` / `high`。切换到不支持该字段的远程服务时，设为 `auto` 以省略。
- Ollama 的默认上下文可能偏小，长对话会丢失前文。需要更大窗口时用 Modelfile 设置 `num_ctx` 并 `ollama create` 派生模型。
- 本地请求受系统代理影响时，设置 `NO_PROXY=localhost,127.0.0.1`。
- 详细说明见 `docs/stage-01-initialization-and-llm-client.md`。

## 工具规划

| 工具 | 功能 | 风险级别 |
| --- | --- | --- |
| `calculator` | 数学表达式求值（AST 白名单，不使用 `eval`） | 低 |
| `read_file` | 读取工作区内文本文件 | 中 |
| `write_file` | 写入工作区内文件（默认禁止覆盖） | 高 |
| `list_dir` | 列出工作区目录 | 低 |
| `analyze_csv` | 读取 CSV 并做排序/统计 | 中 |

## 目录结构

当前：

```text
mini_agent/
├── src/
│   └── mini_agent/
│       ├── __init__.py
│       ├── __main__.py        # python -m mini_agent
│       ├── config.py          # 环境变量、默认值、校验
│       ├── main.py            # CLI 装配与单次调用
│       └── llm/
│           ├── __init__.py
│           ├── client.py      # HTTP、超时、重试、错误归一化
│           ├── mock.py        # 测试用脚本化客户端
│           └── protocol.py    # OpenAI 兼容响应解析
├── tests/
│   ├── test_config.py
│   └── test_llm_client.py
├── docs/                  # 本地设计文档（不纳入版本控制）
├── PRD.md                 # 本地需求文档（不纳入版本控制）
├── uv.lock
├── pyproject.toml
├── README.md
└── .gitignore
```

规划（模块职责与 PRD 一致，按 src 布局落地）：

```text
src/mini_agent/
├── __init__.py
├── config.py
├── llm/               # 模型接入、协议解析、Mock
├── agent/             # 循环、状态、上下文、规划
├── tools/             # 注册表与具体工具
├── memory/            # 会话历史与持久化
├── runtime/           # 权限、限额、执行编排
└── observability/     # 结构化事件与轨迹
tests/                 # 离线单元测试与 e2e
```

只在职责真正出现时创建模块，不预建空文件。

## 开发阶段

| 阶段 | 目标 | 验收 |
| --- | --- | --- |
| 0 | 脚手架与配置 | 可运行入口、配置缺失有明确提示 |
| 1 | 最小 LLM Client | 能调用模型并解析响应，错误可分类 |
| 2 | Agent Loop | 多轮决策，非法输出可恢复，超步数可终止 |
| 3 | Tool Calling | 模型选工具、参数校验、结果回灌 |
| 4 | Memory / Context | 会话可恢复，长对话可裁剪 |
| 5 | Planning | 多工具依赖任务可完成，失败可重试/重规划 |
| 6 | 可靠性 / 评估 | 事件可复盘，离线测试全绿，评估集有结果 |

## 安全边界

- 模型只能请求调用已注册工具，不能执行任意代码。
- `calculator` 使用 AST 白名单求值，禁止 `eval` / `exec`。
- 文件操作限制在 `MINIAGENT_WORKSPACE` 内，路径解析后校验。
- 覆盖已有文件默认拒绝，需显式允许。
- 运行受步数、超时、输出长度与重复调用限制。
- API Key 只从环境变量读取，不写入代码、日志或异常信息。

## 文档说明

设计与过程文档位于本地 `docs/`，需求文档为 `PRD.md`。二者不纳入版本控制，仅作为个人开发参考。

- `docs/stage-01-initialization-and-llm-client.md`：环境初始化与 LLM Client
- `docs/stage-02-agent-loop.md`：Agent Loop 与决策协议（设计稿）

## 许可证

未指定。
