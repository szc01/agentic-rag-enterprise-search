# Day 8 派工说明：进阶检索策略 + 答辩冲刺

> 自包含任务说明，交给 Claude Code 执行。请在项目根目录 `D:\agentic-rag-system` 下启动，按优先级顺序执行。Day 1-7 已完成（见 README「Day 1-7 功能清单」），本文件只列 Day 8 增量。

## 前置条件

- Docker 依赖已启动：`docker compose up -d`（PostgreSQL + pgvector + Redis）。
- `.env` 已配置（DeepSeek key）；BGE embedding / reranker 模型已缓存在 `~/.cache/huggingface/hub`，离线可用，**不要重新下载**。
- 知识库当前 385 chunks / 17 文档（`backend/scripts/eval_data.py` 固定种子可复现），评测集 110 条。
- 开工前先 `git pull`（或确认在 `origin/main` 最新提交之上），Day 8 改动保持干净 diff。

## 现状诊断（对应报告第 8 章已写明的不足/展望）

1. **查询侧无增强**：检索只有单条 query 走「BM25+向量+RRF+Reranker」，未做查询改写 / HyDE / 多路召回（报告 8.3 明确列为未来方向）。
2. **BM25 索引无增量更新**：`backend/app/services/retriever.py` 中 `invalidate_index()` 后 `ensure_index()` 会**全量重建**（报告 8.2 第 1 条不足）。
3. **评测语料为合成文档**、RAGAS 样本仅 22 条（报告 8.2 第 3/4 条）。
4. **无检索性能数据**：答辩被问「单次检索耗时、瓶颈在哪、并发吞吐」时无量化数据（报告 8.2 第 2 条 CPU 吞吐）。

## 任务 1（核心）：查询改写 + HyDE 检索增强

- **目标**：在查询侧加两种增强，做出「baseline vs 增强」的对比实验，补齐报告 8.3 第一条展望。
- **具体**：
  - 新增 `backend/app/services/query_enhance.py`：
    - **查询改写（rewrite）**：用 LLM 把原始 query 改写/扩展为 2-3 个语义变体（同义、补全、消歧），分别检索后结果合并（复用现有 RRF 融合即可）。
    - **HyDE**：用 LLM 生成一段「假设回答文档」，用 `embedding_service.embed_query(假设文档)` 的向量替代原始 query 向量做向量检索（BM25 一路仍用原始 query）。
  - `backend/app/config.py` 加开关：`query_rewrite_enabled: bool = False`、`hyde_enabled: bool = False`（默认关，不影响既有行为）。
  - 在 `HybridRetriever.hybrid_search` 入口按开关接入（或在 `graph.py` 检索编排处接入，二选一，保持一致）。
  - 评测：在 `backend/scripts/eval_retrieval.py` 加 `--enhance {none|rewrite|hyde}` 参数，跑 baseline / rewrite / hyde 三组，输出 top-k / MRR / nDCG@5 对比。
- **验收**：真实跑通；在**复杂查询**（多主题干扰 / 跨语言 / 反向否定）上至少一个增强使 top-1 或 nDCG@5 提升；产出对比表并写入 `backend/output/eval_result.md`（追加「查询增强消融」一节）。

## 任务 2：BM25 索引增量更新

- **目标**：解决「文档增删后 BM25 全量重建」的不足（报告 8.2 第 1 条）。
- **具体**（推荐走较轻的内存增量方案，tsvector 作为可选进阶）：
  - 在 `HybridRetriever` 内用**自定义倒排结构**（`term -> {chunk_id: tf}` + `term -> doc_freq`）替换 `rank_bm25.BM25Okapi` 的批量构建；`build_bm25_index` 首次全量建，新增 `add_chunks` / `remove_chunks` 方法做增量增删。
  - `ingestion.py` 入库、`documents.py` 删除文档时，从「置 dirty 全量重建」改为调用增量方法。
  - BM25 打分公式保持 Okapi BM25（k1=1.5, b=0.75）不变，保证与旧实现检索结果一致。
- **验收**：pytest 全绿（新增增量更新正确性测试：增删文档后检索结果与全量重建一致）；给出「全量重建 vs 增量更新」耗时对比数据（385 chunks 基准 + 模拟 1 万 chunks 估算）。

## 任务 3：真实语料扩充 + RAGAS 扩样本

- **目标**：让评测语料更贴近真实（报告 8.2 第 3/4 条）。
- **具体**：
  - 补充一批**真实公开文档**（如 PostgreSQL / LangChain / FastAPI 官方文档、公开技术白皮书的可公开片段），与合成语料混合入库；或程序化生成更贴近真实分布的文档。
  - `eval_ragas.py` 样本从 22 条扩到 **40+ 条**，覆盖更多难例（不只 5 类轮流，可加权难例）。
- **验收**：知识库规模与来源在 `eval_result.md` 说明清楚；RAGAS 四指标重新跑出并写入 `backend/output/ragas_result.md`，标注样本量。

## 任务 4：检索性能基准（延迟 / 吞吐）

- **目标**：补齐答辩可引用的性能数据（报告 8.2 第 2 条）。
- **具体**：新增 `backend/scripts/benchmark_latency.py`：
  - 单次检索端到端延迟分布（P50 / P95 / P99），分阶段计时（BM25、向量、RRF、Reranker 各自耗时）。
  - 对比「Reranker 开 / 关」的延迟差异；并发吞吐（如 4/8 并发）。
- **验收**：产出 `backend/output/benchmark.md`，含延迟分布表 + 阶段耗时占比，能回答「单次检索约 X ms、瓶颈在 Reranker / 向量检索」。

## 环境坑（务必遵守，否则重蹈覆辙）

1. **启动无代理**：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`（否则 HuggingFace 走代理 502）。
2. **模型已缓存，别重复下载**：BGE 模型在 `~/.cache/huggingface/hub`。
3. **Reranker 用 `predict` 不是 `compute_score`**：本机 sentence-transformers 无 `compute_score`；`predict` 对单标签模型默认已 sigmoid，返回 0-1 概率，勿二次 sigmoid。
4. **CrossEncoder 推理是阻塞操作**，务必 `asyncio.to_thread` 丢线程池。
5. **Python 字符串里中文引号用全角** `"` `"`，别写 ASCII `"` 与字符串定界符冲突（会报 `SyntaxError: invalid character '—'`）。
6. **jieba 已是默认分词**（`_tokenize`），不要改回字符滑动窗口（`_tokenize_char_window` 仅供对比保留）。

## 优先级

**1 > 4 > 2 > 3**：任务 1（查询增强）是核心增量、论文价值最高；任务 4（性能基准）简单且答辩必需；任务 2（增量更新）工程价值高但较重；任务 3（语料）是数据补充。时间不够优先做 1 和 4。
