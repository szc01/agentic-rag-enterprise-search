# Agentic RAG 企业智能搜索与自动调研系统（项目负责人）  2026.03 - 2026.09

- 设计 LangGraph 四阶段 Agent 编排，支持复杂查询规划、检索、审查与综合
- 构建 BM25+pgvector+RRF+BGE-Reranker 混合检索，top-1 74.55%、MRR 0.7889、nDCG@5 0.8026
- 引入 LLM 查询改写与 HyDE，复杂查询 top-1 从 62.12% 提升至 71.21%（+9.09pt）
- 建成 402 chunks/22 文档知识库与 110 条评测集，RAGAS 四指标 0.69/0.62/0.79/0.84
- 工程化 BM25 索引持久化（PG JSONB 快照，冷启动提速 70×）+ Reranker 超时降级（P99 3.13s→1.63s）
- 技术栈：Python / FastAPI / LangGraph / PostgreSQL+pgvector / Redis / BGE / DeepSeek
- 链接：https://github.com/szc01/agentic-rag-enterprise-search
