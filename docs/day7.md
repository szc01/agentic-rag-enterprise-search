# Day 7 派工说明：实验补强 + 论文收尾

> 本文件是交给 Claude Code 的自包含任务说明。Claude Code 看不到项目外的对话，请务必在项目根目录 `D:\agentic-rag-system` 下启动它，并按本文件顺序执行。

## 前置条件（先确认再开工）

- Docker 依赖已启动：`docker compose up -d`（PostgreSQL + pgvector + Redis）。
- `.env` 已配置：至少 `OPENAI_API_KEY`（DeepSeek）、数据库/Redis 连接串有效。
- BGE embedding / reranker 模型已缓存在 `~/.cache/huggingface/hub`（离线可用，**不要重新下载**）。
- 后端真实库已有数据（用于评测）；当前知识库仅 7 文档 11 chunks，任务 1 会扩充。
- 建议开工前先 `git commit` 一次当前状态，Day 7 改动保持干净可审的 diff。

---

## 现状诊断（关键短板，均已定位到文件）

1. 评测集仅 32 条、知识库仅 7 文档 11 chunks → **top-3/top-5 命中率 100% 饱和，无区分度**（论文实验最大硬伤）。见 `backend/output/eval_result.md`。
2. 中文分词是字符滑动窗口（`backend/app/services/retriever.py` 的 `_tokenize`，128-138 行），未用 jieba。
3. RAGAS 生成质量评测**未接线**，但 `ragas`/`datasets` 已在 `requirements.txt`，judge 字段（`judge_model`/`judge_base_url`/`judge_api_key`）已在 `backend/app/config.py` 41-43 行。
4. LangGraph checkpointer **未启用**（`backend/app/graph.py` 210-211 行注释确认；`config.py` 已预留 `checkpoint_postgres_uri` 字段）。

## 任务 1（核心）：评测集 + 知识库扩量，解决 top-3/top-5 饱和

- **目标**：让检索评测有真实区分度，产出能写进论文实验章节的完整数据。
- **具体**：
  - 扩充知识库到 **300–500 chunks**：构造真实企业多主题文档（产品手册 / 技术白皮书 / 制度规范 / FAQ / 研发文档，覆盖互不相关领域，制造检索干扰）。
  - 评测集扩到 **100+ 条**，保持 5 类难度（基线直配 / 同义改写 / 跨语言 / 多主题干扰 / 反向否定），`keyword` 必须是库内 chunk 的真实子串。
  - 新增**消融实验**：`BM25-only` / `向量-only` / `BM25+向量` / `BM25+向量+Reranker` 四组对比，输出完整指标表。
- **验收**：top-3、top-5 均 < 100%（不再饱和），四组消融呈合理递进（完整管线最优）；更新 `backend/output/eval_result.md` + 新增消融对比表。

## 任务 2：BM25 中文分词升级（jieba + 停用词）

- **具体**：`requirements.txt` 加 `jieba`；用 jieba 重写 `retriever.py` 的 `_tokenize`，加入中文停用词表；英文/数字/下划线分词保持不变。
- **验收**：pytest 全绿；用任务 1 的评测集对比「字符滑动窗口 vs jieba」的中文查询命中率，给出对比数据（提升或持平均可，要有数字）。

## 任务 3：RAGAS 端到端生成质量评测接线

- **具体**：写 `backend/scripts/eval_ragas.py`，复用 config 里已有的 judge 字段做 LLM judge，评测 `faithfulness` / `answer_relevancy` / `context_precision` / `context_recall` 四指标，取 20–30 条真实问答样本。
- **验收**：能真实跑通 RAGAS 并输出四指标分数到 `backend/output/ragas_result.md`。

## 任务 4：LangGraph checkpointer 会话持久化 + 收尾清理

- **具体**：
  - 启用 checkpointer（`checkpoint_postgres_uri` 已预留），多轮问答跨请求恢复会话状态。
  - 清理残留：`retriever.py:39` 的「TODO 暂未接入」（Reranker 早已接入，注释过时）；`requirements.txt` 移除未用的 `weasyprint`（PDF 已用 Chrome headless）。
  - 同步文档：README 补 Day 7 清单、更新技术栈与评测章节。
- **验收**：pytest 全绿（应 ≥ 54）；README 与代码一致；git 可干净提交。

## 环境坑（务必遵守，否则重蹈覆辙）

1. **启动无代理**：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`（否则 HuggingFace 走代理 502）。
2. **模型已缓存，别重复下载**：BGE 模型在 `~/.cache/huggingface/hub`，离线模式直接用。
3. **Reranker 用 `predict` 不是 `compute_score`**：本机 sentence-transformers 无 `compute_score`；`predict` 对单标签模型默认已 sigmoid，返回 0-1 概率，勿二次 sigmoid。
4. **CrossEncoder 推理是阻塞操作**，务必 `asyncio.to_thread` 丢线程池，别卡事件循环。
5. **Python 字符串里中文引号用全角** `"` `"`，别写 ASCII `"` 与字符串定界符冲突（会报 `SyntaxError: invalid character '—'`）。

---

## 优先级

**1 > 3 > 2 > 4**：时间不够时务必先做 1 和 3（这是论文实验与「未来展望」闭环的关键）。
