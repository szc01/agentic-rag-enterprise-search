# RAGAS 生成质量评测

- 评测样本：22 条真实问答（query 在 5 类难度中轮流取用，reference=事实陈述原文）
- 检索上下文：完整管线（BM25 + 向量 + RRF + Reranker，top-5）
- 答案生成：主 LLM（DeepSeek）；评分：LLM-as-judge（复用 judge 字段）

| 指标 | 分数 | 说明 |
|---|---|---|
| faithfulness | 0.7455 | 回答是否忠于检索上下文（无编造） |
| answer_relevancy | 0.6341 | 回答与问题的相关程度 |
| context_precision | 0.8371 | 相关上下文在检索结果中的排序精度 |
| context_recall | 0.8636 | 检索结果覆盖参考答案信息的比例 |

