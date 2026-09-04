# Day 9 派工说明：项目收尾 · 答辩冲刺 · 简历沉淀

> 自包含任务说明，交给 Claude Code 执行。请在项目根目录 `D:\agentic-rag-system` 下启动，按优先级顺序执行。Day 1-8 已完成（见 README「Day 1-8 功能清单」与本目录 `day7.md` / `day8.md`），本文件只列 Day 9 增量。
>
> **Day 9 的核心定位**：项目主体功能已闭环，**不再引入新功能**，聚焦三件事——**答辩/演示准备（P0）**、**简历素材沉淀（P0）**、**工程化补强以关闭报告 §8.2 剩余 limitation（P1）**。

## 前置条件

- Docker 依赖已启动：`docker compose up -d`（PostgreSQL + pgvector + Redis）。
- `.env` 已配置（DeepSeek key）；BGE embedding / reranker 模型已缓存在 `~/.cache/huggingface/hub`，离线可用，**不要重新下载**。
- 知识库当前 **402 chunks / 22 文档**（混合合成 + 5 篇真实公开文档片段，Day 8 已完成），评测集 110 条，pytest 65 passed。
- 报告 `report/专业综合工程实践设计报告.docx` 已同步至 Day 8 数字（top-1 74.55% / MRR 0.7889 / nDCG@5 0.8026 / RAGAS 4 指标 44 样本）。
- 演示截图已生成 6 张（`report/images/demo_*.png`：chat / chat_multiturn / dashboard / kb / report / search），任务 2 重在脚本化与文字稿。
- 开工前先 `git status` 确认工作区干净（Day 8 末态应为 `nothing to commit, working tree clean`）。Day 9 改动按"答辩材料 / 工程化 / 报告同步"分若干原子提交。

## 现状诊断

报告 §8.2 当前 4 条 limitation（`scripts/generate_report.py` 第 951-957 行）：

1. **BM25 倒排索引**虽已支持增量更新，但仍为进程内存结构，重启后需重建，未持久化到 PostgreSQL tsvector 等外部索引。
2. **Reranker 在 CPU 推理**带来 ~1.4s 延迟，`backend/output/benchmark.md` 报告 P50=1362.92ms，Reranker 占检索总耗时 ~90%。
3. **真实公开文档占比较小**（402 chunks 中真实语料仅 5 篇片段），与真实企业知识库分布仍有差异。
4. **RAGAS 评测样本仅 44 条**，端到端生成质量评估规模仍有限。

> 此外，用户**临近 2027 届秋招**（求职目标含京东等大厂 AI 技术岗），Day 9 必须沉淀可直接用于简历与面试的素材。

## 任务 1（核心 · P0）：答辩 PPT

**目标**：产出一份 12-15 页的答辩 PPT，覆盖项目全貌，能独立支撑 15-20 分钟答辩。

**必含章节**（页数分布参考）：

| # | 章节 | 页数 | 内容要点 |
|---|------|------|----------|
| 1 | 封面 | 1 | 项目名、姓名、专业、指导教师、日期 |
| 2 | 项目背景 | 2 | 企业知识检索三大痛点（语义不足 / 复杂问题 / 调研耗时）+ Agentic RAG 价值主张 |
| 3 | 需求分析 | 1 | 功能需求 + 非功能需求 + 约束（中文企业语料 / 单机部署 / DeepSeek） |
| 4 | 总体架构 | 2 | 四层架构图（前端 / API 网关 / 业务模块 / 智能体编排） + 四模块（文档/搜索/调研/看板） |
| 5 | 核心算法 | 3 | LangGraph 状态机（Planner→Retrieval→Critic→Synthesizer）+ 混合检索（BM25+pgvector+RRF+BGE-Reranker）+ 查询增强（多查询改写 + HyDE） |
| 6 | 实验结果 | 3 | 四组消融表 + 查询增强消融 + RAGAS 4 指标 + 性能基准 P50/P95 |
| 7 | 总结与展望 | 1 | §8.1 总结 + §8.3 未来方向 |
| 8 | 致谢 | 1 | 简短致谢 + Q&A |

**复用素材**（PPT 制作时直接引用，不要重新造图）：

- `report/images/flow.svg` — 业务流程图
- `report/images/arch.svg` — 总体架构图
- `report/images/usecase.svg` — 用例图
- `report/images/er.svg` — ER 图
- `report/images/eval.svg` — 四组消融柱状图
- `report/images/demo_search.png` / `demo_chat.png` / `demo_report.png` — 演示截图
- `backend/output/benchmark.md` — 性能数据表

**具体步骤**：

1. 用 **python-pptx** 写 `scripts/generate_pptx.py` 生成 `report/答辩.pptx`（或调用 `tencent-pptx` skill，参考其风格生成）。本机字体优先 `微软雅黑` / `SimHei`，无则 fallback 默认。
2. 每页内文字号 **≥ 18pt**、正文 **≥ 14pt**、单页文字 **≤ 200 字**。
3. 第 5/6 章必须含图（架构图、状态机图、消融柱状图各占一整页或半页），用 `python-pptx` 的 `add_picture` 直接插入 SVG/PNG。
4. 页脚加页码与项目名（左：项目名，右：第 X 页 / 共 Y 页）。

**验收**：

- `report/答辩.pptx` 存在，**页数 12-15**（不超过 20）。
- 至少 4 张图（架构图、流程图、消融图、演示截图各 1）。
- 字号与单页字数达标（用 `Presentation().slide_width/height` 间接校验，不强制脚本检查）。
- 打开后无字体回退乱码（关键中文字符渲染正确）。
- 关键数字（top-1 74.55% / RAGAS faithfulness 0.69 / Reranker P50 1362.92ms）与报告 §7 严格一致。

## 任务 2（核心 · P0）：系统演示脚本与文字稿

**目标**：写一份 5-8 分钟的标准 demo 流程脚本（可照搬执行），并补齐/挑选演示截图。

**输出文件**：

- `docs/demo_script.md` — 分镜脚本（Markdown 表格：时间 / 动作 / 讲解词 / 截图路径）
- `report/images/demo/` 目录（可选，若需把演示截图集中）— 把现有 6 张 demo 截图按主题分目录组织

**脚本结构**（每 30-60 秒一个分镜）：

| 时段 | 动作 | 讲解词（≤ 50 字） | 截图 |
|------|------|-------------------|------|
| 0:00-0:30 | 启动系统 + 登录 | 系统基于 FastAPI + pgvector，支持多格式文档... | 启动截图（若无则省略） |
| 0:30-1:30 | 知识库 + 上传 1 篇 PDF | 已索引 402 个文档片段，含真实公开语料 | `demo_kb.png` |
| 1:30-2:30 | 简单问答：「什么是 RAG」 | 基础问答演示，引用溯源 | `demo_search.png` |
| 2:30-3:30 | 复杂查询 + 流式输出 | 复杂问题触发 Agentic RAG 多步检索 | `demo_chat.png` |
| 3:30-4:30 | 多轮对话 + 指代消解 | 第二个问题「它有什么优势」正确解析为 RAG | `demo_chat_multiturn.png` |
| 4:30-5:30 | 一键生成调研报告 + PDF 导出 | Agent 自动生成 5 章节报告，引用可溯 | `demo_report.png` |
| 5:30-6:30 | 运营看板 + 用户反馈 | 检索命中率 / 反馈统计 / Top 文档 | `demo_dashboard.png` |

**验收**：

- 脚本文件存在，可被完全照搬执行（含每一步 curl / 浏览器操作具体路径）。
- 6 张截图都标了文件路径（绝对路径 `D:\agentic-rag-system\report\images\demo_xxx.png`）。
- 讲解词逐字稿**通顺、无术语堆砌**（不出现"基于 Transformer 的双塔架构"这种长句）。
- 总时长 5-8 分钟（讲解词每段 30-60 字 × 6-7 段 = 200-400 字，按 150 字/分钟语速推算）。

## 任务 3（核心 · P0）：简历项目亮点素材

**目标**：沉淀 1 页可直接贴到简历「项目经历」一栏的 4-6 条 bullet points，**带数字、带动作动词**。

**输出**：`docs/resume_bullets.md`

格式示例（**不是模板，是规范**）：

```markdown
# Agentic RAG 企业智能搜索与自动调研系统（项目负责人）  2026.03 - 2026.09
- 设计并实现基于 LangGraph 的 Agentic RAG 四智能体编排（Planner→Retrieval→Critic→Synthesizer），通过 Critic 迭代审查机制使复杂查询 top-1 命中率较单轮 RAG 提升 [N] 个百分点
- 提出 BM25 稀疏检索 + pgvector 稠密检索 + RRF 融合 + BGE-Reranker 精排的混合检索策略，在自建 110 条评测集上达到 top-1 74.55% / MRR 0.7889 / nDCG@5 0.8026
- 引入 LLM 查询改写 + HyDE 检索增强，使复杂查询 top-1 从 62.12% 提升到 71.21%（+9.09pt）
- 实现多轮对话 + 指代消解 + SSE 流式回答 + 引用溯源 + 用户反馈闭环
- 引入 RAGAS 评测体系（faithfulness / answer_relevancy / context_precision / context_recall），44 样本下四项指标分别达到 0.69 / 0.62 / 0.79 / 0.84
- 技术栈：Python / FastAPI / LangGraph / PostgreSQL + pgvector / Redis / BGE / DeepSeek
- 链接：https://github.com/szc01/agentic-rag-enterprise-search
```

**硬性要求**：

- **4-6 条** bullet（少则不饱满，多则失焦）。
- **至少 3 条带量化数字**（命中率 / 延迟 / 样本量 / 提升幅度）。
- **每条 ≤ 60 字**，总字数 ≤ 400 字。
- **STAR 法则**（情境-任务-行动-结果）尽量体现，但**重结果**（数字在前）。
- **不写敏感信息**（学号 / 导师姓名可保留；联系方式 / 身份证号不写）。
- **中文版 + 英文版各一份**（英文版用于投递外企/算法岗，但仅在用户后续要求时再追加，本次只交付中文版）。

**验收**：

- 文件存在，4-6 条 bullet。
- 至少 3 条含数字。
- 字数与 STAR 法则达标（人工目视检查）。
- **数字与报告 §7 / `backend/output/eval_result.md` / `backend/output/ragas_result.md` 严格一致**（不编造）。

## 任务 4（P1 · 工程）：BM25 倒排索引持久化

**目标**：消除报告 §8.2 第 1 条 limitation（"重启后需重建，未持久化到 PostgreSQL tsvector 等外部索引"），让 BM25 索引状态可跨进程保留。

**方案选择**（推荐**轻量级**方案，Elasticsearch 是过度工程）：

**方案 A（推荐）**——在 PostgreSQL 新建表 `bm25_index_state`：

```sql
CREATE TABLE bm25_index_state (
    id          SERIAL PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,    -- 'doc_freq' / 'avg_dl' / 'total_docs' / 'inverted'
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- `HybridRetriever.__init__` 启动时：`SELECT key, value FROM bm25_index_state`，反序列化到 `_doc_freq` / `_avg_dl` / `_total_docs` / 自定义倒排索引。
- 增量更新后（`add_chunks` / `remove_chunks` 末尾）：**异步 + 5s debounce 写回**（用 `asyncio.create_task` 触发一个定时写盘任务）。
- 提供 `GET /api/admin/bm25_status` 接口返回 `last_saved_at` / `chunk_count` / `index_size_bytes`。
- 启动时若表为空 → 走全量构建路径（保持向后兼容）。

**验收**：

- 新增 `backend/app/services/bm25_persistence.py`，封装 load/save/debounce_flush 逻辑。
- 新增 `backend/tests/test_bm25_persistence.py`：
  - test_persistence_round_trip：构造 100 chunks 索引 → 调 save → 模拟重启（new HybridRetriever）→ 调 load → 验证 `_doc_freq` / `_total_docs` 完全一致。
  - test_incremental_persistence：增删 chunks → 触发 debounce → 验证数据库值更新。
- pytest 65 → **≥ 67 passed**。
- `backend/app/services/retriever.py` 重构：在 `ensure_index()` 入口加 try-load from DB，失败则 fallback 全量构建。
- README「Day 1-9 功能清单」追加：Day 9 — BM25 索引持久化到 PostgreSQL。
- `docs/day9.md`（本任务清单）完成情况由用户在交付时勾选。

**报告同步**（任务完成后必做）：

- `scripts/generate_report.py` 第 953 行 `8.2` 第 1 条改为：
  > "（1）BM25 倒排索引已支持持久化到 PostgreSQL，跨进程保留，但单实例重启时仍需从数据库反序列化；后续可迁移到独立搜索服务（如 Elasticsearch）以支撑更大规模数据。"
- 重新生成 `report/专业综合工程实践设计报告.docx`。

## 任务 5（P1 · 工程）：Reranker 性能优化

**目标**：缓解报告 §8.2 第 2 条 limitation（Reranker P50 ~1.4s 是检索主要瓶颈）。

**方案**（**三选二组合**，保守可控）：

**方案 A（必做）**——**超时降级开关**：

- `HybridRetriever.hybrid_search` 加 `rerank_timeout: float = 1.5` 参数（单位：秒）。
- `asyncio.wait_for(reranker.rerank(...), timeout=rerank_timeout)`，超时则**记录日志 + 跳过 Reranker 直接返回 RRF 融合结果**。
- 配置项 `rerank_fallback_on_timeout: bool = True`（默认开）。

**方案 B（推荐）**——**Top-K 截断**：

- Reranker 只对**粗排前 30 个**候选做精排（不是全部 ~110 个），减少推理 token 量。
- 参数 `rerank_top_k: int = 30`，可通过 `HybridRetriever` 构造参数或 config 注入。

**方案 C（可选）**——**预计算缓存**（适合静态语料）：

- `add_chunks` 完成后，**后台**对每个 chunk 跑一次"伪 query"（用 chunk 自身首句）过 Reranker，把分数缓存到 `chunks.rerank_score_static` 列。
- 检索时若有缓存分则直接用 RFF 排序后乘以 0.5 权重 + 动态 Reranker 加权融合。
- **本任务视情况决定是否做**，因实现复杂且对动态 query 效果有限。

**验收**：

- 实现方案 A + B；方案 C 仅在时间充裕且静态语料占比 > 80% 时做。
- 重新跑 `backend/scripts/benchmark_latency.py`：
  - Reranker ON 路径 P50：从 **1362.92ms 下降到 ≤ 900ms**（下降 ≥ 30%）。
  - Reranker OFF 路径 P50：保持 ≤ 60ms 不变。
- 新增 `backend/tests/test_reranker_fallback.py`：注入 mock Reranker 模拟 2s 延迟，验证超时降级不抛异常且返回 RRF 结果。
- pytest 67 → **≥ 68 passed**。
- `backend/output/benchmark.md` 重新生成，附录加"优化后对比表"。

**报告同步**：

- `scripts/generate_report.py` 第 955 行 `8.2` 第 2 条改为：
  > "（2）Embedding 与 Reranker 在 CPU 上推理，已通过超时降级与 Top-K 截断将 Reranker 端到端 P50 延迟从 1362.92ms 降至 [新值]ms，但大批量入库与高并发下吞吐仍受限；后续可引入 GPU 推理或模型服务化部署进一步提升性能。"
- `scripts/generate_report.py` 第 7.5 节同步新数字。
- 重新生成 `report/专业综合工程实践设计报告.docx`。

## 任务 6（P2 · 答辩）：演示问答预演

**目标**：准备 12-15 个高频答辩问题与参考答案，确保答辩现场能 30 秒内给出有结构的回应。

**输出**：`docs/qa_prep.md`

**必含问题**（不限于此）：

1. 为什么不直接用 LangChain？/ 为什么要自建 Agentic 编排？
2. BM25 和向量检索怎么融合的？为什么 RRF？
3. Reranker 为什么能提升？用了什么模型？
4. RAGAS 四个指标分别衡量什么？你的系统分数如何？
5. 性能瓶颈在哪？怎么优化？
6. 怎么解决幻觉问题（faithfulness 不为 1）？
7. 多轮对话怎么实现指代消解的？
8. 部署成本？需要什么硬件？
9. 和商业产品（如阿里云百炼、字节扣子）比差距在哪？
10. 未来怎么扩展？最想做的下一个特性是什么？
11. 知识库规模上限是多少？BM25 和 pgvector 各自的容量边界？
12. 为什么选 DeepSeek 而不是 GPT-4 / Qwen？
13. 检索不到时怎么办？/ 怎么评估"检索失败"？
14. 用户反馈数据怎么用的？有没有学习闭环？
15. 你这个项目最大的创新点是什么？

**每条答案要求**：

- 100-200 字。
- **不堆术语**，能用一句话讲清的就用一句话。
- 关键数字直接引用报告 §7。
- 结尾留 1-2 句"我们下一步..."以应对追问。

**验收**：

- 文件存在，12-15 个问题。
- 每个答案 100-200 字。
- 关键数字与报告 §7 一致。
- 不出现"首先...其次...最后..."这种答辩模板腔（自然对话感）。

## 环境坑（务必遵守，否则重蹈覆辙）

1. **启动无代理**：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`（否则 HuggingFace 走代理 502，DeepSeek 走代理超时）。
2. **模型已缓存，别重复下载**：BGE 模型在 `~/.cache/huggingface/hub`。
3. **Reranker 用 `predict` 不是 `compute_score`**：本机 sentence-transformers 无 `compute_score`；`predict` 对单标签模型默认已 sigmoid，返回 0-1 概率，**勿二次 sigmoid**。
4. **CrossEncoder 推理是阻塞操作**，务必 `asyncio.to_thread` 丢线程池。
5. **Python 字符串里中文引号用全角** `"` `"`，别写 ASCII `"` 与字符串定界符冲突（会报 `SyntaxError: invalid character '—'`）。
6. **jieba 已是默认分词**（`_tokenize`），不要改回字符滑动窗口。
7. **Mermaid 渲染**：节点文字含 `/` 必须用 `["..."]`；dotted edge label `-. "文本" .->` 必须双引号（Day 8 教训）。
8. **PPTX 字体**：本机优先用 `微软雅黑` / `SimHei`，无则 fallback 模板默认字体（`tencent-pptx` skill 已处理）。
9. **报告图渲染**：用 `scripts/render_svgs.py` 走 `file:///` 绝对 URI + device_scale_factor=2（Day 7 教训），**别写 bare filename**。
10. **Git 提交**：本地 commit 后**不要 `git push`**，交由用户终端手动 push（避免后台 GCM 凭据弹窗）。每完成一个任务提交一次，commit 信息清晰（`Day 9: 答辩 PPT 生成` / `Day 9: BM25 索引持久化` 等）。
11. **pytest 命令**：本机用 `C:\Users\27809\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m pytest backend/tests/ -v`（确保隔离环境），或 `python -m pytest`（确认当前 venv 是 `.workbuddy`）。
12. **报告数字一致性**：任何评测数字修改（任务 4/5 完成后），务必**同时**更新 `report/专业综合工程实践设计报告.docx`、`README.md` 顶部核心亮点、`docs/day9.md` 完成情况勾选三处，**避免 Day 7/8 出现过的"代码与报告脱节"问题**。

## 优先级与时间分配

| 任务 | 优先级 | 预计时间 | 求职/答辩价值 | 工程价值 |
|------|--------|----------|----------------|----------|
| 1. 答辩 PPT | **P0** | 3-4h | ⭐⭐⭐⭐⭐ | — |
| 2. 演示脚本 | **P0** | 1-2h | ⭐⭐⭐⭐⭐ | — |
| 3. 简历亮点 | **P0** | 1h | ⭐⭐⭐⭐⭐ | — |
| 4. BM25 持久化 | P1 | 2-3h | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 5. Reranker 优化 | P1 | 2-3h | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 6. 问答预演 | P2 | 1-2h | ⭐⭐⭐⭐ | — |
| **合计** | | **10-15h** | | |

**建议执行顺序**：3 → 1 → 2 → 5 → 4 → 6

理由：
- 任务 3（简历亮点）最简单，1 小时搞定，先收一个"求职直接可用"的成果。
- 任务 1（PPT）需要 3-4 小时连续专注，趁精力好时做。
- 任务 2（演示脚本）依赖任务 1 的 PPT 章节命名。
- 任务 5（Reranker 优化）收益立竿见影（性能数字变好），且对答辩"性能瓶颈"问题有现成答案。
- 任务 4（BM25 持久化）工程量大但价值偏内部，放后面。
- 任务 6（问答预演）最后做，此时对项目细节最熟。

## 交付物清单

| 类别 | 文件 | 任务 | 必需 |
|------|------|------|------|
| 答辩 PPT | `report/答辩.pptx` | 1 | ✅ |
| 演示脚本 | `docs/demo_script.md` | 2 | ✅ |
| 简历亮点 | `docs/resume_bullets.md` | 3 | ✅ |
| 持久化代码 | `backend/app/services/bm25_persistence.py` | 4 | P1 |
| 持久化测试 | `backend/tests/test_bm25_persistence.py` | 4 | P1 |
| 性能优化代码 | `backend/app/services/reranker_optimized.py` 或在 `retriever.py` 内 | 5 | P1 |
| 降级测试 | `backend/tests/test_reranker_fallback.py` | 5 | P1 |
| 性能基准 | `backend/output/benchmark.md`（重生成） | 5 | P1 |
| 报告同步 | `report/专业综合工程实践设计报告.docx`（重生成） | 4/5 | P1 |
| 报告生成脚本 | `scripts/generate_report.py`（更新 §7.5/§8.2） | 4/5 | P1 |
| README 同步 | `README.md`（顶部核心亮点 + Day 1-9 清单） | 全部 | ✅ |
| 问答预演 | `docs/qa_prep.md` | 6 | P2 |
| Git 提交 | 4-6 个原子提交（每个任务一次） | 全部 | ✅ |
| 工作日志 | `docs/day9.md`（本文件）勾选完成情况 | 全部 | ✅ |

## 最终验收

1. ✅ `report/答辩.pptx` 可正常打开，**12-15 页**。
2. ✅ `docs/demo_script.md` 可照搬执行，**总时长 5-8 分钟**。
3. ✅ `docs/resume_bullets.md` **4-6 条带数字**的 bullet。
4. ✅ 报告 §7.5 / §8.2 / §8.3 已同步任务 4/5 后的新数字（如完成 P1 任务）。
5. ✅ pytest 全绿，65 → **≥ 68 passed**（如完成 P1 任务）。
6. ✅ 报告 8 章结构完整，无明显错误（与 Day 8 末态保持一致）。
7. ✅ README 顶部核心亮点 + Day 1-9 清单同步。
8. ✅ Git 工作区干净，所有 commit 信息清晰。
9. ✅ `docs/qa_prep.md`（P2）含 12-15 个问答。
10. ✅ 交付清单中"必需"列全部 ✅，"P1"列尽量完成。
