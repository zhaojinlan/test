# dataAgent — 多智能体推理系统

> LangGraph Supervisor（外层 ReAct）+ AutoGen ConversableAgent（内层 ReAct）

---

## 快速开始

```bash
cd O:\dataAI\dataAgent

# 安装依赖（如尚未安装）
pip install langgraph>=0.0.50 pyautogen>=0.2.0 openai>=1.0.0 requests>=2.31.0

# 运行
python main.py
```

运行后会在同目录生成 `run.log`，包含完整的推理过程日志。

---

## 架构概览

```
┌──────────────────────────────────────────────────────┐
│              LangGraph Supervisor 图                  │
│           （外层 ReAct：条件监督循环）                 │
│                                                      │
│  START → analyze → decompose → supervisor_decide ◄─┐ │
│                                    │ (conditional) │ │
│                        ┌───────────┼───────────┐   │ │
│                        ▼           ▼           ▼   │ │
│                   RESEARCH    ANALYZE     VERIFY   │ │
│                  (CoT子代理) (ToT子代理) (CoT子代理)│ │
│                        │           │           │   │ │
│                        └───────────┴───────────┘   │ │
│                                │                   │ │
│                                └───────────────────┘ │
│                        ▼                             │
│                   SYNTHESIZE → format_answer → END   │
└──────────────────────────────────────────────────────┘
```

### 双层 ReAct 设计

| 层级 | 框架 | 角色 | 说明 |
|------|------|------|------|
| **外层** | LangGraph StateGraph | Supervisor | Thought=决策节点, Action=子代理执行, Observation=状态更新 |
| **内层** | AutoGen ConversableAgent | 子代理 | Thought-Action(search)-Observation 循环 |

---

## 项目结构

```
dataAgent/
├── config/
│   ├── __init__.py
│   └── settings.py          # LLM / 搜索 / 系统配置
├── tools/
│   ├── __init__.py
│   └── bocha_search.py      # 博查搜索 API 封装
├── graph/
│   ├── __init__.py
│   ├── state.py             # LangGraph 状态定义（SupervisorState）
│   ├── nodes.py             # 所有节点函数（8个）
│   └── supervisor.py        # 条件监督图构建
├── agents/
│   ├── __init__.py
│   ├── prompts.py           # 各子代理 system prompt（CoT / ToT）
│   └── react_wrapper.py     # AutoGen ConversableAgent + ReAct 封装
├── utils/
│   ├── __init__.py
│   ├── llm_client.py        # OpenAI 兼容 LLM 调用
│   └── post_process.py      # 答案后处理
├── main.py                  # 入口（含 TeeStream 日志输出到 run.log）
├── requirements.txt
└── Agent.md                 # 本文件
```

> **清理提示**：项目根目录下的 `_check_deps.py`、`_run_test.py`、`_smoke.py` 为调试临时文件，可安全删除。

---

## 修改记录

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 2026-02-18 23:40 | `config/settings.py` | 新建 | LLM(火山方舟deepseek-v3) / 搜索(博查) / 系统参数 |
| 2026-02-18 23:40 | `tools/bocha_search.py` | 新建 | 博查 Web Search API POST 封装 + 结果格式化 |
| 2026-02-18 23:41 | `utils/llm_client.py` | 新建 | OpenAI SDK 封装，供 LangGraph 节点调用 |
| 2026-02-18 23:41 | `utils/post_process.py` | 新建 | 答案标准化：小写/strip/整数化/逗号分号 |
| 2026-02-18 23:42 | `graph/state.py` | 新建 | `SupervisorState` TypedDict + `Annotated` 累积 reducer |
| 2026-02-18 23:42 | `agents/prompts.py` | 新建 | Research(CoT)、Analysis(ToT)、Verify(CoT) 提示词 |
| 2026-02-18 23:43 | `agents/react_wrapper.py` | 新建 | `ReactSubAgent`：ConversableAgent + 手动 ReAct 循环 |
| 2026-02-18 23:44 | `graph/nodes.py` | 新建 | 8 节点：analyze/decompose/supervisor/research/analysis/verify/synthesize/format |
| 2026-02-18 23:45 | `graph/supervisor.py` | 新建 | `build_supervisor_graph()`：条件边 + 循环 |
| 2026-02-18 23:46 | `main.py` | 新建 | 入口 + TeeStream 日志 + 测试问题 |
| 2026-02-18 23:47 | `graph/state.py` | 修改 | 移除 `from __future__ import annotations`，避免 LangGraph reducer 运行时解析失败 |
| 2026-02-18 23:48 | `graph/nodes.py` | 修改 | `post_process_answer` 移到顶层 import，移除 `format_answer` 内的行内 import |
| 2026-02-18 23:50 | `main.py` | 重构 | 延迟导入 graph/config 模块；新增 `TeeStream` 日志同时写入 `run.log` |
| 2026-02-19 00:15 | `../Test/run_agent_submit.py` | 重写 | 去掉 async HTTP API 调用，改为直接 import dataAgent 的 `graph.invoke()` |
| 2026-02-19 00:43 | `../Test/run_agent_submit.py` | 修改 | 新增 TeeStream 日志写入 `submit_run.log`；`▓▓▓` 醒目分隔 + 时间戳 + 进度统计 |
| 2026-02-19 00:47 | `tools/code_executor.py` | 新建 | 安全代码沙箱：AST 白名单 + 受限 builtins + stdout 捕获 + 线程超时 |
| 2026-02-19 00:47 | `agents/react_wrapper.py` | 修改 | `_parse_action()` 支持 `Action: code`；run() 循环新增 code 分支调用 CodeExecutor |
| 2026-02-19 00:47 | `agents/prompts.py` | 修改 | 三个子代理提示词均加入 `Action: code` 工具说明和使用场景 |

<!--
修改详情：

1. **config/settings.py**
   集中管理外部配置。`get_autogen_llm_config()` 返回 AutoGen 所需的 config_list 格式。
   火山方舟 API 兼容 OpenAI 协议，base_url = https://ark.cn-beijing.volces.com/api/v3。

2. **tools/bocha_search.py**
   基于用户提供的 curl 示例实现。POST 方式请求 https://api.bocha.cn/v1/web-search，
   返回格式化文本（标题+URL+摘要+来源+时间）。超时 30 秒，异常返回友好错误字符串。

3. **graph/state.py**
   使用 TypedDict 定义显式状态。evidence_pool 和 reasoning_trace 使用
   Annotated[list, operator.add] 实现 LangGraph 的 add reducer，
   节点只需返回新增元素列表即可自动追加。
   注意：不可使用 from __future__ import annotations，否则 LangGraph 无法在运行时
   resolve Annotated 类型。

4. **agents/react_wrapper.py**
   核心设计：ConversableAgent.generate_reply(messages=[...]) 驱动循环。
   - 正则解析 Action: search + Action Input: <query> 提取搜索请求
   - 正则解析 Final Answer: 判断结束
   - 超过 max_steps 强制总结
   - Observation 截断到 6000 字符避免上下文溢出
   - generate_reply 返回值可能是 str/dict/None，全部处理

5. **graph/nodes.py**
   - supervisor_decide：外层 ReAct 的 Thought。输出 Decision 字段路由
   - 三个执行节点创建 ReactSubAgent 实例运行内层 ReAct
   - format_answer：格式要求含大写示例时跳过小写转换

6. **graph/supervisor.py**
   - add_conditional_edges 实现 Supervisor 路由
   - 三个执行节点 add_edge 回到 supervisor_decide 形成循环
   - SYNTHESIZE → format_answer → END

7. **main.py**
   - TeeStream 将 stdout/stderr 同时写入 run.log（解决 Windows 终端编码问题）
   - 延迟导入 graph/config 模块，确保 TeeStream 先于任何 import 生效
   - 顶层 try/except 捕获异常并写入日志

8. **../Test/run_agent_submit.py（重写）**
   - 去掉 aiohttp + asyncio + call_research_api 的 HTTP API 调用模式
   - 改为 sys.path.insert(0, dataAgent/) 后直接 import graph.supervisor
   - _ensure_graph() 懒加载编译图，所有题目复用同一张图
   - run_one_question() → graph.invoke(initial_state) → final_state["final_answer"]
   - 兼容 "Question"（大写 Q）和 "question"（小写 q）字段名
   - 保留断点续跑、--limit、--trace-dir 功能

9. **../Test/run_agent_submit.py（日志增强）**
   - 新增 TeeStream 将 stdout/stderr 同时写入 submit_run.log（追加模式）
   - setup_logging() 在 main() 最早期调用
   - 每题开始：▓▓▓ 大字 banner（时间戳 + id + 进度 + 问题前100字）
   - 每题结束：─── 分隔线（答案 + 耗时 + 进度统计）
   - 全局结束：### 总结（成功/失败/跳过）
   - 预先统计 total_questions 用于进度显示

10. **tools/code_executor.py（新建）**
    - 安全机制：AST 静态分析白名单（math/re/json/statistics/datetime/decimal/fractions/collections）
    - 阻止危险函数：exec/eval/__import__/open/input + os.system/popen/remove 等
    - 受限 builtins：只保留 abs/int/float/str/len/range/print 等安全函数
    - 预注入常用模块到 safe_globals（math/re/json/datetime/Decimal/Fraction/Counter）
    - exec() + redirect_stdout 捕获 print 输出
    - 如果无 print 输出，尝试 eval 最后一个表达式的值
    - threading.Thread + join(timeout=10) 超时保护

11. **agents/react_wrapper.py（code 工具接入）**
    - _parse_action() 替换原 _parse_action_input()，返回 (action_type, action_input)
    - 正则先匹配 Action: (search|code)，再提取 Action Input
    - code 类型自动去除 ```python / ``` markdown 标记
    - 兼容旧格式：无明确 Action 类型时，若 Action Input 包含代码块则推断为 code
    - run() 循环新增 elif action_type == "code" 分支

12. **agents/prompts.py（code 工具说明）**
    - 三个子代理提示词均新增 Action: code 格式说明和使用场景
    - Research: "数学计算、日期差值、单位换算、字符串格式化"
    - Analysis: "数学运算、日期计算、数值比较"
    - Verify: "核算数值、验证日期差、单位换算"
-->

---

## 关键知识点

### 1. LangGraph 条件监督图
- `StateGraph` + `add_conditional_edges` 实现动态路由
- 路由函数读取 `state["next_action"]` 返回目标节点名
- 循环通过 `add_edge` 从执行节点指回 `supervisor_decide`
- 最后一轮自动强制 `SYNTHESIZE` 防止无限循环

### 2. AutoGen ConversableAgent ReAct
- `ConversableAgent.generate_reply(messages=[...])` 接受 OpenAI 格式消息列表
- `system_message` 由 AutoGen 自动注入为 `_oai_system_message`
- 手动驱动循环（而非 `initiate_chat`）更灵活，可精确控制 Observation 注入时机
- `generate_reply` 返回类型为 `Union[str, Dict, None]`，需全部处理

### 3. 状态设计（LangGraph Reducer）
- `Annotated[list, operator.add]`：节点返回 `[new_item]` 自动追加到列表
- 普通字段（如 `next_action`、`iteration_count`）：节点返回值直接覆盖
- **禁止** `from __future__ import annotations`，否则 Annotated 运行时不可解析

### 4. 思维框架选择
| 子代理 | 思维框架 | 适用场景 |
|--------|----------|----------|
| Research | Chain of Thought (CoT) | 广度搜索，线性推理，逐步收集线索 |
| Analysis | Tree of Thought (ToT) | 深度分析，多路径探索+剪枝，复杂关系推理 |
| Verify   | Chain of Thought (CoT) | 逐条验证事实，线性核查 |

### 5. 答案后处理规则
- 转小写（除非格式要求含大写示例，如 "形如：Alibaba Group Limited"）
- 去除首尾空格
- 纯数字转整数字符串
- 逗号/分号后保留一个空格

### 6. AutoGen 调用链路

```
graph/nodes.py                         agents/react_wrapper.py
 ├─ research_execute()  ──┐
 ├─ analysis_execute()  ──┼─→ ReactSubAgent(name, system_prompt)
 └─ verify_execute()    ──┘      │
                                 ├─ __init__(): autogen.ConversableAgent(name, system_message, llm_config)
                                 └─ run(task, context):
                                      for step in range(max_steps):
                                        response = agent.generate_reply(messages=conversation)
                                        ├─ 解析 Action: search / Action Input: <query>
                                        │   └─ BochaSearchTool.execute(query) → Observation 注入
                                        └─ 解析 Final Answer: → 返回结果
```

- 不用 `initiate_chat()`，手动调用 `generate_reply(messages=[...])` 驱动循环
- `generate_reply` 内部自动拼接 `_oai_system_message` + 传入的 messages
- 返回类型 `Union[str, Dict, None]`，代码中三种情况都处理

### 7. 批量运行架构（`Test/run_agent_submit.py`）

```
run_agent_submit.py
 ├─ setup_logging()          → TeeStream 同时写 stdout + submit_run.log
 ├─ _ensure_graph()          → 懒加载编译 LangGraph 图（全题复用）
 └─ run_submit(input, output, ...)
      ├─ get_processed_ids() → 断点续跑（读已完成 id）
      └─ for each question:
           ├─ ▓▓▓ banner（时间戳 + id + 进度）
           ├─ run_one_question() → graph.invoke() → final_answer
           ├─ 写入 JSONL
           └─ ─── 分隔线（答案 + 耗时 + 统计）
```

### 8. 安全代码执行器（`tools/code_executor.py`）

```
LLM 输出                              CodeExecutor
  Action: code         ──→   1. AST 安全检查（白名单 import + 阻止危险函数）
  Action Input:              2. 构建受限 safe_globals（移除 open/exec/eval/__import__）
  ```python                  3. 预注入 math/re/json/datetime/Decimal/Fraction/Counter
  x = 365 * 24               4. exec(code, safe_globals) + redirect_stdout 捕获输出
  print(x)                   5. 若无 print → eval 最后一个表达式
  ```                        6. threading 超时保护（10秒）
                       ←──   返回 stdout 输出或错误信息作为 Observation
```

- **白名单模块**：math, re, json, statistics, datetime, decimal, fractions, collections, itertools, functools, operator, string
- **受限 builtins**：保留 abs/int/float/str/len/range/print/sorted/max/min 等，移除 open/exec/eval/__import__/compile/globals/locals
- **AST 阻止**：`os.system`、`os.popen`、`os.remove` 等属性调用

### 9. 依赖关系
| 包 | 用途 | 最低版本 |
|----|------|----------|
| langgraph | Supervisor 图框架 | 0.0.50 |
| pyautogen | ConversableAgent 子代理 | 0.2.0 |
| openai | LLM 调用（火山方舟兼容） | 1.0.0 |
| requests | 博查搜索 HTTP 请求 | 2.31.0 |
