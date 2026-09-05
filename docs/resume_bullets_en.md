# Agentic RAG Enterprise Intelligent Search & Auto-Research System (Owner)  Mar–Sep 2026

- Designed a LangGraph-based 4-agent pipeline (Planner → Retrieval → Critic → Synthesizer) with iterative self-correction and a MAX_ITERATIONS=3 guard, and introduced LLM query rewriting + HyDE, lifting top-1 on complex queries from 62.12% to 71.21% (+9.09pt)
- Built hybrid retrieval combining a custom BM25 inverted index (jieba tokenization, 34% smaller vocab) with pgvector HNSW dense search, RRF fusion, and BGE-Reranker, reaching 74.55% top-1 / 0.7889 MRR / 0.8026 nDCG@5 on a self-built 110-query eval set (402 chunks)
- Engineered BM25 index persistence via a PostgreSQL JSONB snapshot (schema-versioned + chunk-count-validated), cutting cold-start index load from 1.8s to 25ms (~70×); added Reranker timeout fallback (asyncio.wait_for 1.5s) that compressed P99 tail latency from 3.13s to 1.63s
- Established a RAGAS evaluation pipeline (LLM-as-judge) over 44 samples — faithfulness 0.6924 / context_precision 0.7853 / context_recall 0.8409 — with 92 pytest cases passing; benchmarked latency (P50 51.36ms without Reranker) and 1/4/8-way concurrency (up to 3.51 qps)
- Stack: Python / FastAPI / LangGraph / PostgreSQL + pgvector / Redis / BGE / DeepSeek / vanilla JS
- Repo: https://github.com/szc01/agentic-rag-enterprise-search
