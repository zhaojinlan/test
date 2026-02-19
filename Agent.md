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
| 2026-02-19 21:00 | `tools/serper_search.py` | 新建 | Serper Google Search API 封装，用于英文查询 |
| 2026-02-19 21:00 | `config/settings.py` | 修改 | 新增 `SERPER_API_KEY` / `SERPER_BASE_URL` / `SERPER_DEFAULT_COUNT` 配置 |
| 2026-02-19 21:00 | `agents/react_wrapper.py` | 修改 | 双搜索引擎语言路由 + 搜索去重（精确+模糊） + LLM 连续失败熔断 |
| 2026-02-19 21:00 | `agents/prompts.py` | 修改 | 三个子代理 prompt 均加入搜索工具注意事项（禁用 Google 语法、语言路由提示） |
| 2026-02-19 21:00 | `graph/nodes.py` | 修改 | `synthesize` prompt 强化纯答案输出规则；`format_answer` 改用 LLM 提取+规则后处理两层架构 |
| 2026-02-19 21:10 | `agents/react_wrapper.py` | 修改 | 搜索引擎选择从语言检测改为模型驱动：`search_google` / `search_bocha` 双 Action |
| 2026-02-19 21:10 | `agents/prompts.py` | 修改 | 三个 prompt 的 Action 格式改为 `search_google` / `search_bocha`，引导模型按内容地域相关性选择引擎 |
| 2026-02-19 22:07 | `agents/react_wrapper.py` | 重写 | 从文本 ReAct 解析改为 AutoGen function calling（assistant + executor 双代理 + initiate_chat） |
| 2026-02-19 22:07 | `agents/prompts.py` | 重写 | 移除手动 Action/Observation 格式，适配 function calling；允许 search_google 使用 Google 高级语法 |
| 2026-02-19 22:31 | `agents/react_wrapper.py` | 重写 | `ReactSubAgent` → `GroupChatOrchestrator`；AutoGen GroupChat（user_proxy + researcher + analyst + verifier + GroupChatManager） |
| 2026-02-19 22:31 | `agents/prompts.py` | 重写 | 三个 prompt 改为 GroupChat 协作版：角色感知、交叉验证、实时互动指令 |
| 2026-02-19 22:31 | `graph/nodes.py` | 重写 | 删除 `supervisor_decide` / `research_execute` / `analysis_execute` / `verify_execute`；新增 `group_chat_execute` |
| 2026-02-19 22:31 | `graph/supervisor.py` | 重写 | 条件循环图 → 线性流水线：analyze → decompose → group_chat → synthesize → format → END |
| 2026-02-19 22:31 | `config/settings.py` | 修改 | 新增 `MAX_GROUP_CHAT_ROUNDS = 20` |
| 2026-02-19 22:31 | `main.py` | 修改 | 架构描述更新为 `LangGraph Pipeline + AutoGen GroupChat` |

<!--
修改详情（2026-02-19 21:00 批次）：

13. **tools/serper_search.py（新建）**
    - 封装 Serper.dev Google Search API（POST https://google.serper.dev/search）
    - 认证方式：X-API-KEY header
    - 解析 organic 搜索结果 + Knowledge Graph（如有）
    - 输出格式与 BochaSearchTool 保持一致（标题/URL/摘要）

14. **config/settings.py（Serper 配置）**
    - SERPER_API_KEY / SERPER_BASE_URL / SERPER_DEFAULT_COUNT
    - 博查注释标注为"中文搜索"，Serper 标注为"英文 Google 搜索"

15. **agents/react_wrapper.py（搜索路由+去重+熔断）**
    - 语言路由：`_has_chinese()` 检测查询是否含中文字符，中文→博查，英文→Serper
    - 搜索去重：`_normalize_query()` 归一化 + `_is_duplicate_query()` 精确/模糊匹配（SequenceMatcher ≥ 0.85）
    - 命中缓存时返回提示引导 agent 换角度，避免浪费步数
    - LLM 连续失败熔断：`consecutive_errors >= 3` 时终止，避免无限循环

16. **agents/prompts.py（搜索工具注意事项）**
    - 三个 prompt 均新增"搜索工具注意事项"段落
    - 明确禁止 site: / intitle: / -排除词 / "" 精确匹配等 Google 高级语法
    - 引导英文问题用英文搜索、中文问题用中文搜索

17. **graph/nodes.py（答案质量提升）**
    - `synthesize` prompt 新增 6 条输出规则，强制只输出答案本身
    - `format_answer` 改为两层架构：
      第一层：LLM 提取纯净答案（去解释文字、语言一致性、格式遵循）
      第二层：`post_process_answer()` 规则后处理（小写/整数化/逗号空格）
    - 如果格式要求含大写示例，跳过小写转换保留 LLM 提取的原始大小写

修改详情（2026-02-19 21:10 批次）：

18. **agents/react_wrapper.py（模型驱动搜索引擎选择）**
    - `_parse_action()` 正则从 `(search|code)` 扩展为 `(search_google|search_bocha|search|code)`
    - `run()` 中搜索分支条件从 `action_type == "search"` 改为 `action_type in ("search_google", "search_bocha")`
    - 移除硬编码的 `_has_chinese()` 语言路由，改由模型通过 Action 类型选择引擎
    - 兼容旧格式 `Action: search`：保留 `_has_chinese()` 作为 fallback 推断引擎
    - 无效 Action 提示文本更新为列出 `search_google` / `search_bocha` / `code` 三个选项

19. **agents/prompts.py（双搜索工具 Prompt）**
    - 三个 prompt 中的 `Action: search` 替换为 `Action: search_google` 和 `Action: search_bocha`
    - 工具选择说明改为"根据搜索内容的地域相关性选择引擎"，而非"根据查询语言选择"
    - 举例：中文问题问国外内容 → search_google + 英文查询；英文问题问中国内容 → search_bocha + 中文查询

修改详情（2026-02-19 22:07 批次 —— Function Calling 重构）：

20. **agents/react_wrapper.py（重写：文本 ReAct → AutoGen Function Calling）**
    **之前**：`generate_reply()` 返回纯文本 → `_parse_action()` 正则匹配 `Action: search_google` → 手动路由执行
    **之后**：`register_for_llm()` + `register_for_execution()` 注册工具 → `initiate_chat()` 驱动 assistant↔executor 对话
    - 删除所有文本解析方法：`_parse_action()`, `_extract_thought()`, `_extract_final_answer()`, `_force_conclusion()`, `_trim_conversation()`
    - 新增 `_register_tools()`：将 `search_google`, `search_bocha`, `run_code` 注册为 function calling 工具
    - 新增 `_execute_search()`, `_execute_code()`：工具执行函数，内含去重逻辑
    - 新增 `_extract_result()`：从 `ChatResult.summary` / `chat_history` 提取最终结果
    - `run()` 改为调用 `self.executor.initiate_chat(self.assistant, ...)`
    - 终止条件：assistant 消息中包含 "TERMINATE"

21. **agents/prompts.py（重写：适配 Function Calling）**
    - 移除手动 `Action: / Action Input:` 格式说明（function calling 由 API 层处理）
    - 工具描述改为概要式（详细 schema 由 `register_for_llm` 的 `description` + `Annotated` 提供）
    - 新增 TERMINATE 终止指令
    - `search_google` 允许 Google 高级语法（"精确匹配"、`site:`、`intitle:` 等）
    - `search_bocha` 明确标注"仅支持自然语言查询"

修改详情（2026-02-19 22:31 批次 —— GroupChat 多智能体协作）：

22. **agents/react_wrapper.py（重写：GroupChat 多智能体协作）**
    **之前**：`ReactSubAgent` 单代理 function calling（assistant + executor 1对1 对话）
    **之后**：`GroupChatOrchestrator` 多代理 GroupChat（user_proxy + researcher + analyst + verifier）
    - 删除 `ReactSubAgent` 类，新建 `GroupChatOrchestrator` 类
    - 4 个代理在同一 `GroupChat` 中交互，共享对话历史
    - `GroupChatManager`（有 LLM）自动选择下一位发言者
    - 工具注册改为循环：3 个 LLM 代理共用 `register_for_llm`，`user_proxy` 统一 `register_for_execution`
    - 搜索去重缓存在 GroupChat 全局共享
    - `run()` 接口从 `(task, context)` 改为 `(question, sub_questions, context)`
    - 新增 `extract_evidence_from_history()` 从对话历史提取证据

23. **agents/prompts.py（GroupChat 协作版 Prompt）**
    - 三个 prompt 均加入角色定位：明确 "你是 GroupChat 中的 researcher/analyst/verifier"
    - 加入协作感知：描述其他代理的角色和能力
    - 加入交叉验证指令：verifier 在 researcher 每次提供信息后即时介入
    - 加入互动规则：质疑不确定信息、补充遗漏线索、修正错误结论

24. **graph/nodes.py（节点简化）**
    - 删除：`supervisor_decide`、`research_execute`、`analysis_execute`、`verify_execute`（4 个节点）
    - 新增：`group_chat_execute`（1 个节点，替代上述 4 个）
    - `group_chat_execute` 创建 `GroupChatOrchestrator` 实例，运行后提取证据和结论
    - 保留：`analyze_question`、`decompose_question`、`synthesize`、`format_answer`

25. **graph/supervisor.py（图结构简化）**
    - **之前**：条件循环图（supervisor_decide → 条件路由 → 子代理 → 回到 supervisor）
    - **之后**：线性流水线（analyze → decompose → group_chat → synthesize → format → END）
    - 删除 `_route_after_supervisor` 函数和所有条件边

26. **config/settings.py**
    - 新增 `MAX_GROUP_CHAT_ROUNDS = 20`（GroupChat 最大对话轮次）

-->

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

### 9. AutoGen GroupChat 多智能体协作架构（`react_wrapper.py`）

```
GroupChatOrchestrator.__init__()
  ├── user_proxy   = ConversableAgent(llm_config=False)       ← 发起对话 + 执行工具
  ├── researcher   = ConversableAgent(RESEARCH_PROMPT, llm)   ← 广度搜索
  ├── analyst      = ConversableAgent(ANALYSIS_PROMPT, llm)   ← 深度分析
  ├── verifier     = ConversableAgent(VERIFY_PROMPT, llm)     ← 事实核查
  ├── _register_tools()
  │     ├── user_proxy.register_for_execution(search_google/bocha/run_code)
  │     └── for agent in [researcher, analyst, verifier]:
  │           agent.register_for_llm(search_google/bocha/run_code)
  ├── groupchat    = GroupChat(agents=[user_proxy, researcher, analyst, verifier])
  └── manager      = GroupChatManager(groupchat, llm_config)  ← 自动选择发言者

GroupChatOrchestrator.run(question, sub_questions, context)
  └── user_proxy.initiate_chat(manager, message=task_prompt)
        ├── manager 选择 researcher 发言
        │     researcher 调用 search_google → user_proxy 执行 → 结果返回
        ├── manager 选择 analyst 发言
        │     analyst 基于 researcher 的发现进行分析
        ├── manager 选择 verifier 发言
        │     verifier 质疑或验证已有结论，可能调用搜索反面验证
        ├── ... 交叉循环 ...
        └── 某代理输出含 "TERMINATE" → manager 检测到 → 对话结束
```

**架构演进对比**：
| 维度 | 串行 Supervisor 循环 | GroupChat 协作 |
|------|---------------------|---------------|
| 代理交互 | 隔离执行，互不可见 | 共享对话，实时可见 |
| 交叉验证 | 验证失败 → 新一轮循环（浪费） | 验证失败 → 即时修正（高效） |
| LangGraph 图 | 条件循环（8 节点） | 线性流水线（5 节点） |
| 搜索去重 | 每个子代理独立缓存 | 全局共享缓存 |

- **search_google**（Serper API）：支持 Google 高级语法（`"精确匹配"`、`site:`、`intitle:` 等）
- **search_bocha**（博查 API）：仅自然语言查询，不支持高级语法
- 两个工具输出格式一致（标题/URL/摘要），对 agent 透明

### 10. 搜索去重机制（`react_wrapper.py`）

```
每次搜索前：
  1. _normalize_query(query)  → 小写 + 去引号 + 合并空格
  2. _is_duplicate_query(norm, cache, threshold=0.85)
     ├── 精确匹配 cache key → 命中
     └── SequenceMatcher.ratio() ≥ 0.85 → 命中
  3. 命中 → 返回缓存 + 提示换角度（不消耗 API 配额）
  4. 未命中 → 执行搜索 → 结果存入 cache
```

- 缓存生命周期：每个 `run()` 调用（即每个子代理执行期间）
- 模糊匹配阈值 `DEDUP_SIMILARITY_THRESHOLD = 0.85`，可在类级别调整
- 命中去重时向 agent 注入提示，引导换不同搜索角度

### 11. LLM 两层答案提取（`graph/nodes.py`）

```
synthesize 节点
  └── LLM（强制纯答案输出规则）→ raw_answer

format_answer 节点
  ├── 第一层：LLM 提取（去解释文字、语言一致性、格式遵循）→ extracted
  └── 第二层：post_process_answer()（小写/整数化/逗号空格）→ processed
       └── 如果 format_requirement 含大写示例 → 跳过小写，保留原始大小写
```

- 不使用正则约束答案格式，完全依赖 LLM 理解题目要求
- `format_answer` 的 LLM prompt 嵌入完整评判规则（名词/数字、语言一致性、整数化等）
- 兜底：LLM 提取失败时退回 `raw.strip()`

### 12. 依赖关系
| 包 | 用途 | 最低版本 |
|----|------|----------|
| langgraph | Supervisor 图框架 | 0.0.50 |
| pyautogen | ConversableAgent 子代理 | 0.2.0 |
| openai | LLM 调用（火山方舟兼容） | 1.0.0 |
| requests | 博查 + Serper 搜索 HTTP 请求 | 2.31.0 |
| difflib | 搜索去重模糊匹配（标准库） | — |
