# 给 Claude Code 的派工命令：Day 9 P0 答辩三件套

> 直接复制下面整段（代码块内）到 Claude Code 对话框执行。配套详细规范见 `docs/day9.md`。

---

```
你是一名工程实践实训答辩材料生成助手，在 Windows 工作。请在 D:\agentic-rag-system 项目根目录下完成 Day 9 P0 三件套：

# 项目背景

- 项目：基于 Agentic RAG 的企业智能搜索与自动调研系统
- 作者：随治诚（郑州轻工业大学计算机科学与技术 2027 届）
- 进度：Day 1-9 已完成；报告 v2 已按学校下发模板对齐（5 章 + 结论 + 仿宋_GB2312 + 18pt 固定行距 + 三类参考文献），git commit b78eaa9
- 技术栈：Python 3.13 / FastAPI / LangGraph / PostgreSQL + pgvector / Redis / BGE-large-zh-v1.5 + BGE-reranker-base / DeepSeek-V3
- 关键数字（直接引用，不允许编造）：
  · 完整管线 top-1 74.55% / MRR 0.7889 / nDCG@5 0.8026
  · 四组消融：BM25-only 70.91% / 向量-only 72.73% / BM25+向量 69.09% / 完整+Reranker 74.55%
  · 查询改写 +9.09pt（复杂查询 62.12% → 71.21%）
  · RAGAS 4 指标（44 样本）：faithfulness 0.6924 / answer_relevancy 0.6156 / context_precision 0.7853 / context_recall 0.8409
  · 单次检索：Reranker OFF P50 51.6ms / ON P50 1362.92ms
  · pytest 65 passed / 知识库 402 chunks / 110 评测 queries / 22 文档

# 任务 1（核心 P0）：答辩 PPT

输出：D:\agentic-rag-system\report\答辩.pptx（12-15 页）

复用素材（直接插入，不要重新画图）：
- D:\agentic-rag-system\report\images\arch.png（总体架构）
- D:\agentic-rag-system\report\images\flow.png（Agentic RAG 工作流）
- D:\agentic-rag-system\report\images\eval.png（四组消融柱状图）
- D:\agentic-rag-system\report\images\usecase.png（用例图）
- D:\agentic-rag-system\report\images\demo_search.png / demo_chat.png / demo_chat_multiturn.png / demo_report.png / demo_dashboard.png（演示截图）
- D:\agentic-rag-system\report\专业综合工程实践设计报告.docx（v2 数据源）
- D:\agentic-rag-system\backend\output\eval_result.md（评测原始数据）
- D:\agentic-rag-system\backend\output\benchmark.md（性能基准）
- D:\agentic-rag-system\backend\output\ragas_result.md（RAGAS 数据）

章节结构：
1. 封面（项目名 + 作者 + 学校 + 日期，28pt）
2. 项目背景（2 页）：企业知识管理三大痛点 + Agentic RAG 价值
3. 需求分析（1 页）：功能 + 非功能 + 约束
4. 总体架构（2 页）：四层架构图 + arch.png + 四模块划分
5. 核心算法（3 页）：
   - LangGraph Planner→Retrieval→Critic→Synthesizer + flow.png
   - 混合检索 BM25 + pgvector + RRF + BGE-Reranker
   - 查询增强 LLM 改写 + HyDE
6. 实验结果（3 页）：
   - 四组消融柱状图（eval.png）
   - 查询增强 +9.09pt 对比
   - RAGAS 4 指标表
   - 性能基准 P50/P95
7. 总结与展望（1 页）
8. 致谢 + Q&A（1 页）

生成方式：用 python-pptx 写 D:\agentic-rag-system\scripts\generate_pptx.py，再运行生成

字号：封面 28pt / 一级标题 24pt / 正文 18pt / 表格 14pt（最低 14pt）

验收：
- 12-15 页
- ≥ 4 张图（arch/flow/eval/demo 各 1）
- 关键数字与报告 v2 一致
- 单页 ≤ 200 字
- 字体不乱码

# 任务 2（P0）：演示脚本与文字稿

输出：D:\agentic-rag-system\docs\demo_script.md

结构：5-8 分钟，每段 30-60 秒

| 时段 | 动作 | 讲解词（≤ 50 字） | 截图路径 |
|------|------|-------------------|----------|
| 0:00-0:30 | 启动系统 | 系统基于 FastAPI + pgvector，支持多格式文档... | （启动截图可省） |
| 0:30-1:30 | 知识库 + 上传 1 篇 PDF | 已索引 402 文档片段，含真实公开语料 | demo_kb.png |
| 1:30-2:30 | 简单问答 | 基础问答演示，引用溯源 | demo_search.png |
| 2:30-3:30 | 复杂查询 + 流式输出 | 复杂问题触发 Agentic RAG 多步检索 | demo_chat.png |
| 3:30-4:30 | 多轮对话 + 指代消解 | 第二个问题「它有什么优势」正确解析为 RAG | demo_chat_multiturn.png |
| 4:30-5:30 | 一键生成调研报告 + PDF 导出 | Agent 自动生成 5 章节报告，引用可溯 | demo_report.png |
| 5:30-6:30 | 运营看板 + 用户反馈 | 检索命中率 / 反馈统计 / Top 文档 | demo_dashboard.png |

6 张 demo 截图已在 D:\agentic-rag-system\report\images\demo_*.png，**不要重新生成**

验收：
- 可照搬执行（每步具体到 curl / 浏览器路径）
- 每张截图有绝对路径
- 讲解词逐字稿通顺、无术语堆砌
- 总时长 5-8 分钟（按 150 字/分钟语速推算）

# 任务 3（P0）：简历项目亮点

输出：D:\agentic-rag-system\docs\resume_bullets.md

格式：

    # Agentic RAG 企业智能搜索与自动调研系统（项目负责人）  2026.03 - 2026.09
    - [成果 1，带数字]
    - [成果 2，带数字]
    - [成果 3，带数字]
    - [成果 4，带数字]
    - [成果 5（可选）]
    - 技术栈：Python / FastAPI / LangGraph / PostgreSQL + pgvector / Redis / BGE / DeepSeek
    - 链接：https://github.com/szc01/agentic-rag-enterprise-search

硬性要求：
- 4-6 条 bullet
- 至少 3 条带量化数字（74.55% / 0.7889 / 0.8026 / 0.69·0.62·0.79·0.84 / +9.09pt / 65 passed / 402 chunks 等）
- 每条 ≤ 60 字，总字数 ≤ 400
- STAR 法则（重结果，数字在前）
- 数字与报告 v2 / backend/output/*.md 严格一致，不编造

可选后续追加：英文版（仅在用户后续要求时再做，本次只交付中文版）。

# 环境与已知坑

1. 启动无代理：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`（必须，否则 HuggingFace 502 / DeepSeek 超时）
2. Python 命令：用 venv 的 `C:\Users\27809\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（已装 python-docx / python-pptx / jieba / ragas 等）
3. 图片渲染：用 scripts/render_svgs.py 走 file:/// 绝对 URI（不要 bare filename，Day 7 教训：会触发 Chrome DNS error 页面）
4. Mermaid：节点含 / 必须用 ["..."] 引号；dotted edge label 用 `-. "文本" .->`（Day 8 教训）
5. PPT 字体：优先 微软雅黑 / SimHei，无则 fallback 默认
6. Git 提交：本地 commit 后不要 push（避免后台 GCM 凭据弹窗，由用户手动 push）
7. pytest：完整路径 `C:\Users\27809\.workbuddy\binaries\python\envs\default\Scripts\python.exe -m pytest backend/tests/ -v`
8. 报告数字一致性：任何评测数字修改务必同时更新 report/专业综合工程实践设计报告.docx、README.md、docs/day9.md 三处，避免 Day 7/8 出现过的"代码与报告脱节"问题

# 完成后汇报

请简要汇报：
- 用了多少时间
- PPT 路径 + 页数
- 演示脚本路径 + 总时长
- 简历 bullet 条数 + 总字数
- 有无遗漏 / 异常

按 docs/day9.md 完整规范执行 P0 三个任务即可。P1（BM25 持久化 / Reranker 优化）和 P2（演示问答预演）后续再做。
```