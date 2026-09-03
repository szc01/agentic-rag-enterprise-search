# 检索性能基准

- 采样查询：30 条（来自 110 条评测集等距抽样），top-5 检索
- 环境：CPU 推理（BGE-large-zh-v1.5 + bge-reranker-base），PostgreSQL + pgvector

## 单次检索端到端延迟

| 配置 | P50 | P95 | P99 | 均值 |
|---|---|---|---|---|
| Reranker OFF | 51.60ms | 54.26ms | 113.10ms | 54.42ms |
| Reranker ON | 1362.92ms | 1680.06ms | 3130.82ms | 1460.17ms |

## 分阶段耗时（均值，Reranker OFF）

| 阶段 | 耗时 | 占比 |
|---|---|---|
| BM25 稀疏检索 | 0.29ms | 0.6% |
| 向量检索（pgvector） | 47.99ms | 93.3% |
| RRF 融合 | 0.03ms | 0.1% |
| chunk 回填 | 3.14ms | 6.1% |
| Reranker | 0.00ms | 0.0% |

## Reranker 开 / 关延迟对比

| 配置 | 端到端均值 | Reranker 阶段均值 |
|---|---|---|
| Reranker OFF | 54.42ms | 0.00ms |
| Reranker ON | 1460.17ms | 1310.72ms |

## 并发吞吐（完整管线，Reranker ON）

| 并发度 | 吞吐 |
|---|---|
| 1 | 0.52 queries/s |
| 4 | 0.76 queries/s |
| 8 | 0.80 queries/s |

## BM25 索引维护耗时（全量重建 vs 增量更新）

- 基准语料：385 chunks；增量批次：49 chunks（一个合成文档）

| 操作 | 耗时（当前 385 chunks） | 估算（1 万 chunks） |
|---|---|---|
| 全量重建 | 52.93 ms | 1374.75 ms |
| 增量新增（49 chunks） | 7.54 ms | 7.54 ms |
| 增量删除（49 chunks） | 0.37 ms | ~0.37 ms |

> 增量更新耗时与「新增/删除的 chunk 数量」相关、与语料总量无关，故 1 万 chunks 下增量新增仍约数毫秒级，远优于全量重建（线性增长）。

> 结论：单次检索端到端约 1460.17ms，瓶颈在 Reranker（CrossEncoder 逐对精排）；关闭 Reranker 后延迟显著下降。
