# 多智能体推理系统 — 设计与变更记录

## 架构概览（v4.0 Send API 并行研究架构）

```
┌──────────────────────────────────────────────────────────────────┐
│                     主图（LangGraph + Send API）                    │
│                                                                  │
│  ┌──────────────┐                                                │
│  │ DecomposePlan│   奥卡姆剃刀：只为缺口生成子问题                     │
│  │  (ToT)       │                                                │
│  └──────┬───────┘                                                │
│         │ Send API（动态并行分支）                                    │
│         ├──────────────────────────────────┐                     │
│         ▼              ▼              ▼    │                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ Research     │ │ Research     │ │ Research     │  并行执行      │
│  │ Branch Q1   │ │ Branch Q2   │ │ Branch Q3   │  (search →    │
│  │ (CoT)       │ │ (CoT)       │ │ (CoT)       │   reflect →   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   baike验证 → │
│         │              │              │             证据提取)    │
│         └──────────────┼──────────────┘                         │
│                        ▼ 聚合                                    │
│               ┌──────────────┐                                   │
│    不充分      │ GlobalVerify │  推理链完整性判断                     │
│  ┌────────────│  (GoT)       │  (充分/不充分，非刚性%)              │
│  │            └──────┬───────┘                                   │
│  ▼                   │ 充分 or MAX_LOOPS                         │
│  DecomposePlan       ▼                                           │
│  (仅补缺口)    ┌──────────────┐   ┌────────────┐                │
│               │GlobalSummary │──▶│FormatAnswer │──▶END           │
│               │  (CoT)       │   └────────────┘                 │
│               └──────────────┘                                   │
└──────────────────────────────────────────────────────────────────┘
```

**v3.1→v4.0 核心变化**：
- 使用 LangGraph **Send API** 实现子问题**并行研究**（广度搜索）
- 用**推理链完整性判断**取代刚性 80% 覆盖率阈值
- 遵循**奥卡姆剃刀**：只为推理链缺口生成新子问题，不重复已覆盖内容
- **自动百科验证**：研究分支发现实体后自动触发百度百科验证
- **剪枝机制**：无效搜索方向标记为 pruned，不再重复

**4个智能体节点**：
- **DecomposePlan (ToT)**：奥卡姆剃刀拆分，证据驱动缺口分析
- **ResearchBranch (CoT)**：并行研究（搜索→反思→百科验证→证据提取）
- **GlobalVerify (GoT)**：推理链完整性评估 + 剪枝建议
- **GlobalSummary (CoT)**：基于推理链推导最终答案

**工具**：`bocha_search` + `serper_search` + `baike_search`（自动验证），LangChain `@tool`

## 项目结构

```
dataAgent/
├── config/settings.py         # API密钥、模型、系统参数
├── tools/search.py            # 搜索工具 @tool（博查 + Serper + 百科）
├── agents/prompts.py          # 6个提示词（ToT/CoT/GoT）
├── graph/
│   ├── state.py               # Evidence + SubQuestion + AgentState（Send API）
│   ├── nodes.py               # 5个节点函数（含并行 research_branch）
│   └── supervisor.py          # 图构建 + Send API 路由
├── utils/answer_formatter.py  # LLM 答案归一化
├── main.py                    # 入口
└── requirements.txt
```

---

## 变更记录

### 2025-02-22 第十六次修改（并行独立性 + 查询去重 + 多跳交叉验证 — 修复强制通过时的幻觉答案）

**需求**（来自 id=86 推理失败分析）：
Agent 处理一个三跳关联问题（小微企业调研组成员 ↔ 体育锻炼论文作者 ↔ 80年代空难机组成员同名），耗时 508s 跑满 4 轮 MAX_LOOPS，产出 13 条证据全部标记 low/medium 且明确表示"未获得有效信息"。GlobalVerify 明确输出"无法给出确定答案"，但被强制通过后 GlobalSummary 凭空编造了"林春霞"（仅满足 3 个条件中的 1 个）。

**根因分析（4 项）**：
1. **依赖型子问题被并行执行**：Q2"根据上一问题确定的空难事故，查找机组成员名单"依赖 Q1 结果，但被 Send API 同时派发，Q2 无上下文执行，浪费搜索配额
2. **搜索查询跨轮次语义重复**：4 轮中对空难的搜索关键词几乎相同（仅"20世纪80年代"↔"1980年至1989年"的措辞变化），DecomposePlan 未获得已失败查询的具体内容和结果
3. **强制通过后 GlobalSummary 幻觉**：MAX_LOOPS 触发强制 `is_sufficient=True`，但 GLOBAL_SUMMARY_PROMPT 指令"不要回答'无法确定'"，LLM 从单一证据中随机选了"林春霞"
4. **多跳问题缺乏交叉验证**：GlobalSummary 未要求答案同时满足问题中所有条件，仅匹配单一条件的实体被当作最终答案

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 11:42 | `graph/state.py` | `AgentState` | 新增字段 | 新增 `force_passed: bool`，标记是否因 MAX_LOOPS 强制通过 |
| 11:42 | `config/settings.py` | L33 | 参数调整 | `MAX_BAIKE_VERIFY`: 1→2，允许每个研究分支更多百科验证 |
| 11:42 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 核心原则 | 新增规则5、6 | 规则5：并行独立——所有子问题并行执行，禁止引用其他子问题结果；规则6：查询多样性——失败后必须换用完全不同的策略 |
| 11:42 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 上下文 | 新增参数 | 新增 `{failed_queries}` 占位符，向 LLM 展示已尝试的搜索方向及结果摘要 |
| 11:42 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 禁止事项 | 修改规则3、新增5-6 | 规则3 强化：禁止语义重复（微调措辞≠新查询）；规则5：禁止依赖型子问题；规则6：连续失败应反思术语理解 |
| 11:42 | `agents/prompts.py` | `GLOBAL_SUMMARY_PROMPT` 推理步骤 | 新增步骤5、修改步骤6 | 步骤5：多条件交叉验证——多跳问题答案必须同时满足所有条件；步骤6：替换"不要回答无法确定"为更精细的指导 |
| 11:42 | `graph/nodes.py` | 新增函数 | 新增 | `_failed_queries_summary()`：从已完成子问题+证据池构建搜索历史摘要 |
| 11:42 | `graph/nodes.py` | `decompose_plan` | 修改 | 调用 `_failed_queries_summary()` 并传入 prompt |
| 11:42 | `graph/nodes.py` | `global_verify` | 修改 | 强制通过时设置 `force_passed=True` 并写入状态 |
| 11:42 | `main.py` | `initial_state` | 新增 | 初始化 `force_passed: False` |
| 11:42 | `Test/run_agent_submit.py` | `initial_state` | 重写 | 更新为 Send API 架构的正确字段（移除废弃的 `current_question_id` 等旧字段） |

<!-- 
#### 核心设计详解

##### 1. 并行独立性约束（DECOMPOSE_PLAN_PROMPT 规则5）
Send API 将所有 pending 子问题同时派发执行，每个分支独立运行、互不通信。
旧行为：LLM 生成 Q2"根据上一问题确定的空难事故，查找机组成员名单"→ Q2 执行时 Q1 尚未完成 → Q2 搜索无上下文 → 浪费配额
新行为：prompt 明确"所有子问题将被同时并行执行，每个必须完全自包含"→ LLM 不再生成依赖型子问题

##### 2. 搜索历史去重（_failed_queries_summary + {failed_queries}）
旧行为：DecomposePlan 只看到"已完成的子问题"文本和"证据池"，不知道具体用了什么查询、得到了什么结果 → 生成语义相同的新查询
新行为：`_failed_queries_summary()` 将每个已完成子问题的查询文本 + 对应证据摘要（含可靠性）组合展示 → LLM 清楚知道哪些方向已试过且失败

##### 3. 多跳交叉验证（GLOBAL_SUMMARY_PROMPT 步骤5）
旧行为：Summary 从证据池中选"与最多证据一致的"实体 → "林春霞"仅出现在小微企业报告证据中，但因是唯一具体人名被选为答案
新行为：新增"多条件交叉验证"步骤 → 多跳问题答案必须被验证为同时满足所有条件 → 仅满足单一条件的实体不应作为最终答案

##### 4. Test runner 状态同步（run_agent_submit.py）
旧行为：initial_state 使用废弃字段（current_question_id, is_verified 等），与当前 Send API 架构不匹配，可能导致 LangGraph 运行时警告或异常
新行为：更新为与 main.py 一致的 AgentState 字段，包含 force_passed 新字段
-->

---

### 2025-02-22 第十五次修改（假设审计机制 — 修复解读固化导致的推理死循环）

**需求**（来自 id=82 推理失败分析）：
Agent 在处理 Q82 时，将"微软研究院在西海岸的首个分部"解读为"远离总部的第一个卫星办公室"（BARC, 1995年），而实际上微软研究院 1991 年创立时的总部 Redmond, WA 本身就在西海岸，即为"首个分部"。Agent 发现 1991（火山）vs 1995（BARC）矛盾后，连续 3 轮搜索试图用新事实调和，从未质疑自己的解读——这是典型的**解读固化**（interpretation fixation）。

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 11:29 | `agents/prompts.py` | `GLOBAL_VERIFY_PROMPT` | 新增步骤 2.5 | 新增「假设审计」：当推理链出现矛盾时，列出所有隐含假设 → 逐一翻转 → 检查矛盾是否消失 → 奥卡姆剃刀选最简解释 → 警惕搜索死循环 |
| 11:29 | `agents/prompts.py` | `GLOBAL_VERIFY_PROMPT` 输出格式 | 新增 | 新增 `## 假设审计` 输出区块，确保 LLM 实际产出审计内容 |
| 11:29 | `agents/prompts.py` | `GLOBAL_VERIFY_PROMPT` 步骤 3 | 修改 | 增加提示：矛盾经假设审计消除后应判断为「充分」，不要继续搜索 |
| 11:29 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 逆向推理 | 修改 | 新增多义解读提示：关键术语可能有多种合理解读，列出所有可能，不要过早锁死一种 |

**设计要点**：
- **解读固化的根因**：`GLOBAL_VERIFY_PROMPT` 只有「缺口分析」（搜索更多事实），没有「假设审计」（质疑自己的理解）。矛盾出现时 Agent 只会搜索，不会反思自己的解读
- **假设审计四步法**：列出隐含假设 → 逐一翻转 → 检查矛盾是否消失 → 奥卡姆剃刀选最简解释
- **搜索死循环检测**：连续两轮无法解决同一矛盾 → 问题极大概率在解读上
- **逆向推理多义性**：在问题拆分阶段就识别歧义术语的多种解读，避免下游推理被单一解读锁死

---

### 2025-02-22 第十四次修改（LLM Function Calling 工具选择 — 移除过程式查询重构）

**需求**：
1. 移除硬编码的过程式查询重构逻辑（`_reformulate_query`、`_has_chinese`、`_execute_search`、`_extract_baike_entities`），改由 LLM 通过 function calling 自主选择搜索工具
2. 所有搜索工具统一通过 `bind_tools` 绑定到 LLM，LLM 根据问题语言和内容动态选择合适的工具
3. 移除 prompt 中的问题相关示例（如元胞自动机），替换为中性示例
4. 更新 `DECOMPOSE_PLAN_PROMPT` 输出格式字段名（`子问题：`）

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 01:03 | `graph/nodes.py` | imports | 修改 | 新增 `RESEARCH_SEARCH_PROMPT` 导入 |
| 01:03 | `graph/nodes.py` | `_execute_search` | 删除 | 移除过程式搜索分发（被 `bind_tools` 替代） |
| 01:03 | `graph/nodes.py` | `_has_chinese` | 删除 | 移除中文检测（`tools/search.py` 中仍保留供 `auto_search` 使用） |
| 01:03 | `graph/nodes.py` | `_reformulate_query` | 删除 | 移除引擎/查询格式校验（LLM 自主选择工具即隐式完成格式匹配） |
| 01:03 | `graph/nodes.py` | `_extract_baike_entities` | 删除 | 移除正则解析百科实体（LLM 反思时通过 function calling 直接调用 `baike_search`） |
| 01:03 | `graph/nodes.py` | `research_branch` 阶段1 | 重写 | `llm.bind_tools([bocha_search, serper_search, baike_search])` → LLM 选择工具 → 执行工具调用；fallback 到 `auto_search` |
| 01:03 | `graph/nodes.py` | `research_branch` 阶段2 | 重写 | `llm.bind_tools([baike_search])` → LLM 反思时可选调用百科验证；`MAX_BAIKE_VERIFY` 限制调用次数 |
| 01:03 | `graph/nodes.py` | `decompose_plan` 解析 | 修改 | 新增 `子问题：` 字段名支持（匹配更新后的 prompt 输出格式） |
| 01:03 | `tools/search.py` | `bocha_search` docstring | 修改 | 示例从元胞自动机改为火影忍者（中性示例） |
| 01:03 | `tools/search.py` | `ALL_SEARCH_TOOLS` | 修改 | 新增 `baike_search`（三工具列表供 `bind_tools` 使用） |

**设计要点**：
- **工具选择权交给 LLM**：`bind_tools` 让 LLM 根据 docstring 理解每个工具的适用场景，自主决定调用哪个（可多选）
- **两阶段 function calling**：搜索阶段绑定三个工具，反思阶段只绑定 `baike_search`（约束验证范围）
- **Fallback 机制**：LLM 未选择任何工具时降级到 `auto_search`（语言检测自动分发）
- **移除的代码量**：约 80 行过程式逻辑 → 由 LLM 推理替代，提升灵活性和可维护性

---

### 2025-02-22 第十三次修改（搜索引擎格式校验 + 双向推理 + 证据稳定性）

**需求**（来自日志观察）：
1. 搜索引擎未使用正确格式的查询（中文查询发给serper、关键词片段发给bocha）
2. 证据有时一开始对得上但后续被推翻（假设被当作确认事实）
3. 不是所有问题需要正序解决——双向推理（正向+逆向）+ 渐进聚焦效果更好

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 00:28 | `graph/nodes.py` | `decompose_plan` 解析 | 修改 | 清除 `**`/`#`/`` ` `` markdown 格式泄漏；支持新字段名 `搜索查询：`、`期望发现：`；去除引号包裹 |
| 00:28 | `graph/nodes.py` | 新增 `_reformulate_query` | 新增 | 引擎/查询格式自动校验：中文→serper 降级为 bocha；纯英文→bocha 降级为 serper；长句→baike 降级为 bocha |
| 00:28 | `graph/nodes.py` | `research_branch` | 修改 | 搜索前调用 `_reformulate_query` 校验格式 |
| 00:28 | `graph/nodes.py` | `_extract_baike_entities` | 修改 | 去除编号前缀、markdown 格式、括号注释（修复 `1.  **米尔内站 (南极)**` 问题） |
| 00:28 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` | 重写 | 新增双向推理（正向+逆向）；聚焦分组（避免同一目标多个冗余查询）；`问题：`→`搜索查询：`；`目的：`→`期望发现：`；✅/❌ 格式示例；禁止 markdown 格式 |
| 00:28 | `agents/prompts.py` | `RESEARCH_REFLECT_PROMPT` | 修改 | 新增步骤3「证据稳定性检验」：区分硬证据 vs 软假设；输出格式改为分别列出硬证据和软假设 |
| 00:28 | `agents/prompts.py` | `RESEARCH_EVIDENCE_PROMPT` | 修改 | 强调严格区分确认事实和推测假设；推测部分必须标注；细化可靠性评估标准 |

---

### 2025-02-21 第十二次修改（Send API 并行研究架构 — 完整重构）

**需求**：现有顺序执行架构不够灵活，首轮覆盖不足时后续难以追赶（证据池膨胀）。需要：
1. 遵循奥卡姆剃刀：若非必要，勿增证据或问题
2. 用推理链完整性判断取代刚性 80% 覆盖率
3. 修复搜索词条不遵循提示词的问题
4. 增加百度百科使用频率（做验证）
5. 使用 LangGraph Send API 实现子问题并行研究（广度搜索 + 深度分析）

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 18:45 | `graph/state.py` | 全文 | 重写 | 新增 `current_branch_question`、`completed_question_ids`（`operator.add`）、`reasoning_chain`、`is_sufficient`；移除 `current_question_id`、`current_reflection`、`local_summary_count`、`verification_result`、`high_medium_resolved`、`is_verified` |
| 18:45 | `agents/prompts.py` | 全文 | 重写 | `DECOMPOSE_PLAN_PROMPT` 新增奥卡姆剃刀原则 + `completed_questions` 参数；`SEARCH_REFLECT_PROMPT` → `RESEARCH_REFLECT_PROMPT`（新增百科验证实体提取步骤）；`LOCAL_SUMMARY_PROMPT` → `RESEARCH_EVIDENCE_PROMPT`（支持百科补充）；`GLOBAL_VERIFY_PROMPT` 改为推理链完整性评估（充分/不充分）；`GLOBAL_SUMMARY_PROMPT` 使用 `reasoning_chain` |
| 18:45 | `graph/nodes.py` | 全文 | 重写 | 移除 `search_reflect`、`local_summary`；新增 `research_branch`（搜索→反思→百科验证→证据提取全流程）；新增 `_extract_baike_entities`、`_completed_questions_summary`；`global_verify` 改为推理链评估；`global_summary` 使用推理链 |
| 18:45 | `graph/supervisor.py` | 全文 | 重写 | 引入 `from langgraph.types import Send`；`route_to_research` 返回 `Send` 对象列表实现并行分支；`route_after_verify` 基于 `is_sufficient` 判断；移除 `route_after_local_summary`、`VERIFY_INTERVAL` |
| 18:45 | `config/settings.py` | L29-33 | 修改 | 移除 `VERIFY_INTERVAL`、`RESOLUTION_THRESHOLD`；`MAX_LOOPS` 12→4（并行后每轮处理所有子问题）；新增 `MAX_BAIKE_VERIFY=1` |
| 18:45 | `main.py` | L62-75, L103 | 修改 | 初始状态新增 `current_branch_question`、`completed_question_ids`、`reasoning_chain`、`is_sufficient`；移除旧字段；打印改为推理链充分性 |

<!--
#### 核心设计详解

##### 1. Send API 并行研究（最核心变化）
旧架构：decompose_plan → search_reflect → local_summary → ... （串行，一次处理一个子问题）
新架构：decompose_plan → Send × N → research_branch（并行处理所有子问题） → global_verify

```python
from langgraph.types import Send

def route_to_research(state):
    pending = [sq for sq in state["sub_questions"] if sq["status"] == "pending"]
    return [Send("research_branch", {"current_branch_question": sq, ...}) for sq in pending]
```

每个 Send 创建一个独立的 research_branch 执行实例，所有实例并行运行。
返回的 evidence_pool（Annotated[list, operator.add]）自动累积所有分支的证据。

##### 2. 奥卡姆剃刀（DecomposePlan）
- 新增 `completed_questions` 参数：告诉 LLM 哪些已完成，不要重复
- 限制最多 4 个子问题（旧版是 5 个）
- 提示词强调「只为缺口生成子问题」

##### 3. 推理链评估（取代 80% 覆盖率）
旧：覆盖率 = (已解决高+中) / (总高+中) >= 0.8
新：LLM 判断推理链是否「充分」—— 能从证据逻辑推导出答案即为充分
- 更灵活：3 条高质量证据可能就够，不需要凑百分比
- 更智能：LLM 理解推理链逻辑，而非简单计数

##### 4. 自动百科验证（ResearchBranch）
研究分支在反思阶段提取「建议百科验证的实体」，自动触发 baike_search：
- 反思 prompt 新增步骤5：提取 1-2 个最值得百科验证的实体
- _extract_baike_entities() 解析反思输出中的实体列表
- 自动调用 baike_search 获取百科内容，作为证据提取的补充输入

##### 5. 剪枝机制
- SubQuestion.status 新增 "pruned" 状态
- GlobalVerify 输出「剪枝建议」，告诉下一轮 DecomposePlan 哪些方向应放弃
- 已剪枝的子问题不会被重新生成
-->

---

### 2025-02-21 第十一次修改（搜索引擎结果数量调整）

**需求**：增加搜索引擎返回结果数量，提升信息覆盖面。

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 16:30 | `config/settings.py` | L17, L22 | 修改 | `BOCHA_DEFAULT_COUNT`: 10→25, `SERPER_DEFAULT_NUM`: 10→25 |

**说明**：
- `bocha`（中文搜索）和 `serper`（Google搜索）的结果数量从 10 增加到 25
- `baike`（百度百科）返回的是完整词条内容，不受此参数影响，保持原样

---

### 2025-02-21 第十次修改（全局验证 Markdown 解析 Bug 修复 + Baike 引擎使用指引优化）

**问题诊断**：
GlobalVerify 节点中 LLM 输出 `**验证通过**：是`（带 markdown 加粗 `**`），但代码用 `"验证通过：是" in conclusion` 做精确子串匹配。`**` 夹在中间导致匹配永远失败，`is_verified` 始终为 `False`，系统即使已经找到正确答案也不会停止，陷入无效循环直到 `MAX_LOOPS`。覆盖率解析同理失败（`**覆盖率**：90%` 无法被正则匹配）。

**根因**：`global_verify` 函数直接对 LLM 原始输出做子串/正则匹配，未考虑 LLM 习惯性输出 markdown 格式符号。

**影响**：所有问题都会多跑数轮无效搜索（每轮消耗 API 调用 + 时间），严重浪费资源。例如 id=10 问题在第 6 次总结后 GlobalVerify 已输出"验证通过：是"和正确答案"雷佳音和易烊千玺"，但因解析失败又多跑了 2 轮（Q14、Q15）完全冗余的搜索。

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 16:15 | `graph/nodes.py` | `global_verify` L443-463 | 重写 | 在解析前统一剥离 markdown 格式符号，覆盖率正则改为非贪婪匹配 |
| 16:15 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 规则3 | 修改 | 强化 baike 引擎使用指引：明确适用场景、典型用法、非必要不使用原则 |

<!--
#### 核心知识点

##### 1. LLM 输出 Markdown 格式污染问题
LLM（尤其是 GPT-4/Claude 等）在结构化输出中习惯性使用 markdown 格式：
- `**加粗**`、`*斜体*`、`- 列表前缀`、`## 标题`
- 当代码需要从 LLM 输出中提取关键字段时，必须先清洗格式符号
- 推荐做法：`content.replace("**", "").replace("*", "")` + `re.sub(r'^[\s\-]+', '', ..., flags=re.MULTILINE)`
- 这是一个通用陷阱，适用于所有从 LLM 输出中做字符串匹配的场景

##### 2. 修复前后对比
修复前（匹配失败）：
  LLM 输出: `**验证通过**：是`  →  `"验证通过：是" in text`  →  False
  LLM 输出: `**覆盖率**：(5+4)/(5+5) = 90%`  →  正则匹配失败  →  coverage = 0%

修复后（匹配成功）：
  清洗后: `验证通过：是`  →  `"验证通过：是" in text`  →  True
  清洗后: `覆盖率：(5+4)/(5+5) = 90%`  →  非贪婪正则  →  coverage = 90%

##### 3. Baike 引擎使用原则
- 适用：已知具体实体名称，需百科级详情（生平、作品列表、角色关系）
- 不适用：探索性搜索、多关键词组合查询、问句式查询
- 传参：仅接受单个实体名词（如"张欣""猫眼三姐妹"），禁止问句或短语
- 原则：非必要不使用，bocha/serper 能覆盖时优先用它们
-->

---

### 2025-02-21 第九次修改（候选集穷举验证 + 多锚点联合查询策略）

**问题诊断**：
agent 发现候选人列表（如配音员名单"范蕾颖、张欣、姚培华、赵晴、黄笑嬿"）后，只验证了部分候选就放弃整个候选集转向其他搜索路径。实际上 Bocha 搜索结果中已明确包含答案（"张欣(男性配音演员) → 2007年《贞观之治》长孙无忌(马少骅 饰)"），但因同名干扰和缺乏系统化验证机制而遗漏。

**根因**（两项）：
1. **候选集穷举验证缺失**：系统无"验证队列"机制，不会对每个候选逐一执行定向验证查询
2. **多锚点联合查询缺失**：单独搜索"张欣"噪声极大（同名多人），应组合多个已知锚点"张欣 贞观之治 配音"精确命中

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 14:22 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 规则10 | 新增 | 候选集穷举验证规则：必须逐一验证每个候选实体 |
| 14:22 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 规则11 | 新增 | 多锚点联合查询规则：组合多个锚点减少噪声 |
| 14:22 | `agents/prompts.py` | `SEARCH_REFLECT_PROMPT` 步骤3.7 | 新增 | 多锚点交叉命中检测：识别同时命中多个锚点的高价值结果 |
| 14:22 | `agents/prompts.py` | `SEARCH_REFLECT_PROMPT` 步骤3.8 | 新增 | 候选验证状态追踪：✓已验证/✗已排除/?待验证 |
| 14:22 | `agents/prompts.py` | `SEARCH_REFLECT_PROMPT` 输出格式 | 新增 | "多锚点命中"和"候选验证状态"输出区 |
| 14:22 | `agents/prompts.py` | `LOCAL_SUMMARY_PROMPT` 规则4 | 新增 | 证据陈述中保留候选验证进度 |

<!--
#### 核心概念

##### 1. 候选集穷举验证（Exhaustive Candidate Verification）
当搜索发现一组候选实体（如 N 个人名），需确认其中哪个满足目标条件时：
- 为每个未验证候选生成独立的验证查询
- 绝对禁止只验证部分候选就放弃
- 只有全部候选都被验证或排除后，才能转向其他搜索方向
- 验证状态三态：✓已验证 / ✗已排除 / ?待验证

##### 2. 多锚点联合查询（Multi-Anchor Joint Query）
当已有多个确认锚点时，将它们组合在同一查询中：
- 单锚点查询："张欣" → 噪声极大（同名多人）
- 多锚点联合："张欣 贞观之治 配音角色" → 精确命中
- 原理：多个锚点的交集远小于单个锚点的结果集，大幅降低同名多义干扰

##### 3. 多锚点交叉命中检测（Multi-Anchor Hit Detection）
在反思阶段，检测搜索结果中是否有同一条结果同时提及多个已知锚点：
- 同时出现 "张欣" + "贞观之治" + "长孙无忌" → 极高价值，必须完整提取
- 注意同名多义陷阱：区分北京女性配音演员张欣 vs 上海男性配音演员张欣
-->

---

### 2025-02-21 第八次修改（URL 深读解析优化 + baike 传参约束）

**问题诊断**：
1. `fetch_url_content` 抓取搜狗百科页面后，`_strip_html` 仅移除 `<script>/<style>/<noscript>`，大量导航/侧边栏/推荐噪声占满字符限额，导致文章深处的"国语版配音"表格被 8000 字符截断丢失
2. `baike` 引擎 prompt 约束不够，模型可能传入问句（如"猫眼三姐妹的配音演员是谁？"）而非纯实体名

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 13:49 | `tools/search.py` | `_strip_html` | 重写 | 新增移除 `nav/header/footer/aside/svg/template/iframe/form` 及噪声 div |
| 13:49 | `tools/search.py` | 新增 | `_extract_article_body` | 正则匹配百科/wiki 页面正文容器，优先提取主体内容 |
| 13:49 | `tools/search.py` | 新增 | `_ARTICLE_BODY_PATTERNS` | 搜狗百科/百度百科/维基百科/通用 article 标签的正文容器正则 |
| 13:49 | `tools/search.py` | `fetch_url_content` | 重写 | 先尝试 `_extract_article_body` 提取正文，失败再全页 strip；`max_chars` 8000→15000 |
| 13:49 | `graph/nodes.py` | `_deep_read_promising_urls` | 参数修改 | `max_chars` 6000→15000 |
| 13:49 | `agents/prompts.py` | 规则3 | 强化约束 | baike 查询必须是纯实体名词，新增错误/正确示例对比 |
| 13:49 | `agents/prompts.py` | 输出格式 | 新增示例 | 子问题列表增加 baike 引擎输出格式示例 |

<!--
#### 修改详解

##### 1. _strip_html 增强（tools/search.py）
旧版只移除 script/style/noscript，新版额外移除：
- 结构噪声标签：`nav, header, footer, aside, svg, template, iframe, form`
- 噪声 div：class/id 含 `sidebar, recommend, comment, ad-, breadcrumb, related-, share-, copyright` 等

##### 2. _extract_article_body 正文提取（tools/search.py）
按优先级尝试匹配百科页面的正文容器：
- 搜狗百科：`lemma_content` / `lemma-content`
- 百度百科：`main-content` / `lemmaWgt-lemmaSummary`
- 维基百科：`mw-parser-output`
- 通用：`<article>` 标签 或 class 含 `article/content/main-body/entry`
匹配成功且纯文本>200字则返回该区域 HTML，否则回退全页

##### 3. max_chars 提升
- `fetch_url_content` 默认：8000→15000
- `_deep_read_promising_urls` 调用：6000→15000
- 百科页面的"国语版配音"等深层表格信息不再被截断

##### 4. baike prompt 强化（agents/prompts.py）
- 规则3 增加错误/正确对比示例
- 错误："猫眼三姐妹大陆国语版男主角的配音演员是谁？""刘德华 电影 作品列表"
- 正确："猫眼三姐妹""刘德华""SpaceX""内海俊夫"
- 输出格式区增加 baike 引擎示例模板
-->

---

### 2025-02-21 第七次修改（新增百度百科精确查询引擎）

**需求**：原有搜索引擎（bocha/serper）返回的是网页摘要，对于百科类信息密集页面会丢失表格/列表细节。新增百度百科 API 作为精确实体查询引擎，可直接获取词条完整内容。

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 13:18 | `config/settings.py` | 新增配置 | `BAIKE_API_KEY`、`BAIKE_LIST_URL`、`BAIKE_CONTENT_URL` |
| 13:18 | `tools/search.py` | 新增函数 | `_call_baike_list()`、`_call_baike_content()`、`_format_baike_content()`、`baike_search` tool |
| 13:18 | `graph/nodes.py` | 修改 | `_execute_search` 新增 `baike` 分支；引擎解析新增 `baike` 识别；baike 跳过 deep-read |
| 13:18 | `agents/prompts.py` | 修改规则 | `DECOMPOSE_PLAN_PROMPT` 规则3 新增 baike 引擎说明 |

**百度百科 API 架构**：
- `get_list_by_title`：根据词条名获取义项列表（lemma_id, title, desc, url）
- `get_content`：根据词条名获取完整内容
- `baike_search` tool：先获取义项列表，再获取词条内容，合并输出
- 查询限制：只能输入**单个实体名称**，不能是问句

---

### 2025-02-21 第六次修改（搜索深度优化 — 关闭 summary + URL 深读）

**问题诊断**：Bocha API 使用 `summary: True` 让 AI 对每个搜索结果做摘要，百度百科等页面中的**表格/列表型信息**（如配音演员表）在摘要过程中被丢失。浏览器直接搜索同样的查询可以看到完整的百度百科页面内容。

**根因**：`tools/search.py` 中 `_call_bocha()` 的 `"summary": True` 参数导致信息损失，且系统无能力读取完整网页内容。

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 11:53 | `tools/search.py` | 参数修改 | `summary: True` → `summary: False`，返回原始 snippet |
| 11:53 | `tools/search.py` | 新增函数 | `_strip_html()` + `fetch_url_content(url)` URL 页面内容读取 |
| 11:53 | `graph/nodes.py` | 新增函数 | `_deep_read_promising_urls()` 识别并读取高价值 URL |
| 11:53 | `graph/nodes.py` | 修改流程 | `search_reflect` 中搜索后自动深读百科/wiki 类页面 |
| 11:53 | `graph/nodes.py` | 增大截断 | reflect prompt 输入从 8000→12000 chars |

<!--
#### 修改详解

##### 1. 关闭 Bocha AI 摘要（tools/search.py）
- `"summary": True` → `"summary": False`
- 效果：返回原始 snippet 而非 AI 摘要，减少信息损失

##### 2. URL 内容读取（tools/search.py）
- `_strip_html()`：轻量级 HTML→文本转换（regex），不依赖 BeautifulSoup
- `fetch_url_content(url, max_chars=8000)`：请求 URL 并提取纯文本

##### 3. 搜索后自动深读（graph/nodes.py）
- `_HIGH_VALUE_URL_PATTERNS`：百科/wiki 类 URL 模式列表
- `_deep_read_promising_urls()`：从搜索结果中找到高价值 URL，自动读取最多 2 个页面
- 在 `search_reflect` 中，搜索结果返回后自动调用深读，将完整页面内容追加到搜索结果中
- LLM 反思时能看到完整的百科页面内容（包括表格/列表）
-->

---

### 2025-02-21 第五次修改（搜索质量优化 — 反指代 + 演绎推理）

**问题诊断**：运行 `submit_run2.log` 显示两个系统性缺陷：
1. **搜索查询含指代词**：Q3 生成查询 `"这部动漫大陆国语版男主角的配音演员是谁？"`，其中"这部动漫"是指代词，搜索引擎无上下文，导致搜索结果偏离目标
2. **发现关键实体但未深挖**：系统在豆丁网搜索结果中发现配音名单"范蕾颖、张欣、姚培华、赵晴、黄笑嬿"，但未通过排除法推理出"张欣"极可能是男主角配音，反而错误判定"均为女性配音演员"

**根因分析（3项）**：
1. `DECOMPOSE_PLAN_PROMPT` 规则中禁止了占位符和元指令，但**未禁止指代性词语**（"这部""那个""该"等），导致 LLM 生成含指代的查询
2. `SEARCH_REFLECT_PROMPT` 只有实体提取和交叉关联步骤，**缺少演绎推理环节**（排除法、性别推断），无法从已知信息推导未知
3. `LOCAL_SUMMARY_PROMPT` 未要求保留推理假设，导致即使反思中偶有推断也会在证据浓缩时丢失

| 时间 | 文件 | 位置 | 修改方法 | 说明 |
|------|------|------|----------|------|
| 10:16 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 核心规则 | 新增规则8 | 禁止指代词，要求用具体实体名替换 |
| 10:16 | `agents/prompts.py` | `DECOMPOSE_PLAN_PROMPT` 核心规则 | 新增规则9 | 发现未验证人名时必须生成定向追查子问题 |
| 10:16 | `agents/prompts.py` | `SEARCH_REFLECT_PROMPT` 反思步骤 | 新增步骤3.5 | 演绎推理与假设形成（排除法+性别推断） |
| 10:16 | `agents/prompts.py` | `SEARCH_REFLECT_PROMPT` 输出格式 | 新增输出节 | "演绎推理与假设"输出区域 |
| 10:16 | `agents/prompts.py` | `LOCAL_SUMMARY_PROMPT` 要求 | 新增要求3 | 假设必须纳入证据陈述，标注"推测" |

<!--
#### 修改详解

##### 1. 反指代规则（DECOMPOSE_PLAN_PROMPT 规则8）
- 问题：LLM 生成子问题时使用"这部""那个"等指代词，但搜索引擎是无状态的，不知道指代的是什么
- 修复：明确禁止所有指代性词语，并给出错误/正确示例对比
- 错误：`"这部动漫大陆国语版男主角的配音演员是谁？"`
- 正确：`"《猫眼三姐妹》大陆国语版男主角内海俊夫的配音演员是谁？"`

##### 2. 定向追查规则（DECOMPOSE_PLAN_PROMPT 规则9）
- 问题：证据池发现了"张欣"等人名但从未生成以其为核心的搜索查询
- 修复：当证据池有未验证角色的人名时，必须生成"张欣 配音演员 配音作品"类型的定向追查

##### 3. 演绎推理步骤（SEARCH_REFLECT_PROMPT 步骤3.5）
- 问题：发现5人配音名单后，未尝试将已知3姐妹映射到3人，通过排除法推断剩余2人的角色
- 修复：新增排除法、性别/特征推断、假设形成三个子步骤
- 示例：5人名单 - 3姐妹(姚培华/范蕾颖/赵晴) = 剩余张欣+黄笑嬿 → 张欣(可为男名) + 内海俊夫(男角色) → 假设：张欣是内海俊夫配音

##### 4. 假设保留（LOCAL_SUMMARY_PROMPT 要求3）
- 问题：即使反思阶段形成了推断，证据浓缩时也会丢失
- 修复：要求将假设纳入证据陈述，标注"推测"，确保下游节点可读取
-->

### 关键知识点补充

#### 8. 搜索查询的无状态性
每次搜索请求是独立的，搜索引擎没有会话记忆。查询中的指代词（"这部""那个"）会导致搜索引擎按字面理解，返回无关结果。**所有查询必须自包含**，用具体实体名称替代所有指代。

#### 9. 演绎推理在信息筛选中的价值
当搜索返回一组实体（如人名列表）时，不应仅做"提取+记录"，还应结合已有证据进行**排除法推理**：
- 将已确认的映射关系排除
- 分析剩余实体与未解决问题的匹配度
- 形成可验证的假设，驱动后续定向搜索

这类推理能力是 Agent 从"信息收集者"升级为"信息分析者"的关键。

---

### 2025-02-21 第四次修改（证据池架构 v2 — 逻辑闭环修复）

**问题诊断**：运行 `run_log.txt` 显示系统已在 E4 中发现关键实体"RepRapPro"，但系统从未基于此实体进行追查，导致覆盖率始终为 0%，最终输出"无法确定"。

**根因分析（6项）**：
1. 控制台打印截断（`[:70]`、`[:80]` 等），用户无法看到完整内容
2. 搜索结果内容量不足（snippet `[:300]`、结果只取 8 条、反思内容 `[:4000]`）
3. **路由死循环**（最关键）：`global_verify` 每次添加 3 个新子问题 → 路由总是看到 pending → 永远不回 `decompose_plan` → 证据池无法驱动重新规划
4. `global_verify` 生成的子问题是元指令（"搜索xxx"），不是有效查询
5. `engine="both"` 将中文查询同时发给 serper（Google），浪费且无效
6. 提示词缺乏"证据驱动迭代"指引，发现实体后不知道追查

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 00:30 | `graph/nodes.py` | 移除截断 | 所有 `print()` 中的 `[:N]...` 截断全部移除 |
| 00:30 | `tools/search.py` | 增大内容 | snippet 从 `[:300]` → `[:600]`，移除 `[:8]` 结果数限制 |
| 00:30 | `graph/nodes.py` | 增大内容 | `raw_results` 5000→10000, `search_results` 4000→8000, `reflection` 3000→6000, `verification` 3000→6000 |
| 00:30 | `graph/nodes.py` | **删除代码** | `global_verify` 中移除"补充搜索建议"解析和子问题生成逻辑（约30行） |
| 00:30 | `graph/supervisor.py` | **修改路由** | `route_after_global_verify`：删除 `search_reflect` 路径，未通过时**始终**回到 `decompose_plan` |
| 00:30 | `agents/prompts.py` | **完全重写** | 6 个提示词全部重写为 v2 版本，见下方详细说明 |
| 00:30 | `graph/nodes.py` | 修改搜索 | `engine="both"` 改用 `auto_search` 自动语言路由，不再双发 |
| 00:30 | `graph/nodes.py` | 增加打印 | 新增完整搜索结果、反思内容、验证输出的全文打印 |

<!--
#### 核心修复详解

##### 1. 路由修复（最关键）
旧路由：global_verify → 添加3个新子问题 → route_after_global_verify 看到 pending → search_reflect → 永远不回 decompose_plan
新路由：global_verify → 只验证不添加子问题 → route_after_global_verify 未通过 → **始终** decompose_plan → 用证据池生成追查查询

##### 2. 提示词 v2 核心变化
- DECOMPOSE_PLAN_PROMPT：新增"证据驱动的多路径分析"——如果证据池有具体实体（如RepRapPro），必须以这些实体为核心生成追查子问题。明确禁止 `both` 引擎（每个子问题只用一个）。禁止元指令前缀（"搜索"、"查找"）。
- SEARCH_REFLECT_PROMPT：新增步骤3"与已有证据的交叉关联"和步骤4"关键发现总结"。强调实体提取是最重要的步骤。
- LOCAL_SUMMARY_PROMPT：强制要求保留具体实体名称（英文名+中文名）。给出好/差示例对比。
- GLOBAL_VERIFY_PROMPT：移除"补充搜索建议"输出，改为"线索方向"（仅供下轮 decompose_plan 参考）。覆盖率评估增加"发现具体实体也算部分解决"的宽松标准。
- GLOBAL_SUMMARY_PROMPT：明确禁止回答"无法确定"，要求即使证据不完整也给出最佳推断。

##### 3. 搜索引擎路由
旧：engine="both" → 同一个中文查询同时发 bocha 和 serper → serper 收到中文查询无效
新：engine="both" → auto_search 自动检测语言 → 中文走 bocha，英文走 serper
提示词明确要求每个子问题只指定一个引擎（bocha 或 serper），需要双语搜索时拆成两个独立子问题。
-->

### 2025-02-20 第三次修改（证据池架构重构）

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 23:49 | `config/settings.py` | 修改参数 | 删除旧参数，新增 `MAX_LOOPS=12`, `VERIFY_INTERVAL=2`, `RESOLUTION_THRESHOLD=0.8` |
| 23:49 | `graph/state.py` | 完全重写 | 新增 `Evidence`/`SubQuestion`(带priority)/`AgentState`(含evidence_pool) |
| 23:49 | `agents/prompts.py` | 完全重写 | 5个节点专用提示词 + 格式化提示词，见下方 |
| 23:49 | `tools/search.py` | 修改描述 | `bocha_search` 描述改为支持自然语言句子输入 |
| 23:49 | `graph/nodes.py` | 新建文件 | 6个节点函数：decompose_plan/search_reflect/local_summary/global_verify/global_summary/format_answer |
| 23:49 | `graph/supervisor.py` | 完全重写 | 新图结构 + 2个路由函数，约120行 |
| 23:49 | `graph/research_subgraph.py` | 清空为stub | 已废弃，逻辑迁移到 nodes.py |
| 23:49 | `main.py` | 重写状态初始化 | 使用 `AgentState` 替代 `SupervisorState` |

<!-- 
#### 1. graph/state.py — 证据池状态设计
核心变更：
- Evidence TypedDict：id, source_question_id, statement(陈述性语句), source_urls, reliability(high/medium/low)
- SubQuestion 新增字段：priority(高/中/低), search_engine(bocha/serper/both), raw_results, reflection
- SubQuestion 移除字段：answer, confidence, key_findings（被 Evidence 替代）
- AgentState 新增：evidence_pool(Annotated累积), anchor_analysis, current_reflection, local_summary_count, verification_result, high_medium_resolved, is_verified
- evidence_pool 使用 Annotated[list, operator.add] 实现累积式追加

#### 2. agents/prompts.py — 5+1个节点提示词
核心变更：
- DECOMPOSE_PLAN_PROMPT (ToT)：锚点提取 + 多路径分析 + 优先级规划。强制bocha用自然语言句子、serper用英文关键词
- SEARCH_REFLECT_PROMPT (CoT)：4步反思（相关性过滤→实体提取→交叉验证→信息增量）
- LOCAL_SUMMARY_PROMPT (CoT)：浓缩为一句陈述性语句 + 可靠性评估
- GLOBAL_VERIFY_PROMPT (GoT)：证据关联图→推理链→覆盖度评估→缺口分析。覆盖率公式=(已解决高+中)/(总高+中)
- GLOBAL_SUMMARY_PROMPT (CoT)：按逻辑排列证据→逐步推导→最终答案
- FORMAT_ANSWER_PROMPT：保持不变

#### 3. graph/nodes.py — 6个节点函数
核心变更：
- decompose_plan()：解析 "## 锚点分析" 和 "## 子问题列表" 格式，支持引擎/重要性/目的三个属性行。占位符过滤。
- search_reflect()：_pick_next_question()按优先级排序（高→中→低），engine=both时同时调bocha和serper。调LLM反思过滤。
- local_summary()：解析 "证据陈述：" 和 "可靠性：" 行，构造Evidence对象，利用operator.add累积到evidence_pool。
- global_verify()：正则提取覆盖率百分比，解析验证通过/补充建议。覆盖率≥RESOLUTION_THRESHOLD或loop_count≥MAX_LOOPS时通过。
- global_summary()：解析 "## 最终答案" 行，多级fallback。
- format_answer()：复用 FORMAT_ANSWER_PROMPT。

#### 4. graph/supervisor.py — 新图构建
核心变更：
- 2个路由函数：route_after_local_summary()（每VERIFY_INTERVAL次→验证，有pending→搜索，否则→验证）、route_after_global_verify()（通过→总结，超限→总结，有pending→搜索，否则→重新规划）
- 图边：decompose_plan→search_reflect（固定）, search_reflect→local_summary（固定）, local_summary→条件, global_verify→条件, global_summary→format_answer→END（固定）

#### 5. tools/search.py — bocha自然语言
核心变更：
- bocha_search 的 docstring 改为 "输入应为完整的中文自然语言句子"
- 提示LLM生成完整句子而非关键词堆叠

#### 6. main.py — 新初始状态
核心变更：
- 使用 AgentState 替代 SupervisorState
- 新增 evidence_pool, anchor_analysis, local_summary_count 等字段初始化
- 打印证据池摘要和覆盖率
-->

---

### 2025-02-20 第二次修改

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 23:11 | `config/settings.py` | 新增配置 | Serper API 配置 |
| 23:11 | `tools/search.py` | 完全重写 | 双搜索引擎 + @tool |
| 23:11 | `agents/prompts.py` | 完全重写 | 禁止占位符 + 双引擎指引 |
| 23:11 | `graph/state.py` | 新增字段 | `search_query_details` |
| 23:11 | `graph/research_subgraph.py` | 完全重写 | 双引擎 + [engine] 标签 |
| 23:11 | `graph/supervisor.py` | 完全重写 | 自动推进 + 占位符过滤 |

### 2025-02-20 第一次创建

| 时间 | 文件 | 修改方法 | 说明 |
|------|------|----------|------|
| 22:40 | 全部文件 | 新建 | 初始创建 Supervisor + Research 子代理架构 |

---

## 关键设计知识点

### 1. 证据池（Evidence Pool）— Session Memory
```python
evidence_pool: Annotated[list, operator.add]  # 累积式，节点返回 [new_evidence] 自动追加
```
- 每个 `research_branch` 生成一条 `Evidence`，通过 `operator.add` 累积到池中
- 多个并行分支的证据自动合并（Send API + reducer）
- `global_verify` 读取全池进行推理链构建

### 2. LangGraph Send API — 动态并行分支
```python
from langgraph.types import Send

def route_to_research(state):
    pending = [sq for sq in state["sub_questions"] if sq["status"] == "pending"]
    return [
        Send("research_branch", {
            "original_question": state["original_question"],
            "evidence_pool": state.get("evidence_pool", []),
            "current_branch_question": sq,
            "completed_question_ids": [],
        })
        for sq in pending
    ]
```
- `Send` 为每个子问题创建独立执行实例，**并行**运行
- 所有实例的返回值通过 `Annotated[list, operator.add]` 自动合并
- `completed_question_ids` 累积所有已完成的子问题 ID

### 3. 奥卡姆剃刀原则
- `DECOMPOSE_PLAN_PROMPT` 接收 `completed_questions` 参数，告知 LLM 已完成的子问题
- 限制最多 4 个子问题（广度适中）
- 只为推理链缺口生成新子问题，不重复已覆盖的方面

### 4. 推理链完整性评估（取代刚性覆盖率）
旧：`覆盖率 = (已解决高+中) / (总高+中) >= 80%`
新：LLM 判断推理链是否「充分」—— 能逻辑推导出答案即为充分
- 更灵活：高质量证据即使数量少也可能充分
- 更智能：LLM 理解逻辑完整性，而非简单计数
- 解析字段：`充分性：充分/不充分`（剥离 markdown 后匹配）

### 5. 思维结构选型
| 节点 | 思维结构 | 原因 |
|------|----------|------|
| DecomposePlan | 思维树(ToT) | 多路径分析 + 奥卡姆剃刀筛选 |
| ResearchBranch | 思维链(CoT) | 搜索→反思→百科验证→证据提取 |
| GlobalVerify | 思维图(GoT) | 证据关联图 + 推理链完整性判断 |
| GlobalSummary | 思维链(CoT) | 基于推理链线性推导答案 |

### 6. LLM Function Calling 工具选择（v4.1）
- **搜索阶段**：`llm.bind_tools([bocha_search, serper_search, baike_search])` — LLM 根据 docstring 自主选择工具（可多选）
- **反思阶段**：`llm.bind_tools([baike_search])` — LLM 可选调用百科验证关键实体
- **Fallback**：LLM 未选择任何工具时降级到 `auto_search`（语言检测自动分发）
- 移除了过程式 `_reformulate_query`、`_execute_search`、`_extract_baike_entities`
- 工具 docstring 是 LLM 选择依据，需保持清晰准确

### 7. 搜索工具 docstring（LLM 选择依据）
- **bocha_search**：`"搜索中文互联网内容（支持自然语言句子）...输入应为完整的中文自然语言句子"`
- **serper_search**：`"搜索国际互联网内容（Google）...输入搜索查询字符串"`
- **baike_search**：`"精确查询百度百科词条内容...输入应为准确的实体名称"`
- LLM 根据问题语言和内容匹配最合适的工具，无需硬编码规则
