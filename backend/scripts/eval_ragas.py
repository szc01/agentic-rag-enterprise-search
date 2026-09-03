"""RAGAS 生成质量评测（Task 3）：faithfulness / answer_relevancy / context_precision / context_recall

用法（在 backend 目录执行）：
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/eval_ragas.py

说明：
  - 复用 config.py 里的 judge 字段（judge_model / judge_base_url / judge_api_key）做 LLM-as-judge。
  - 取知识库真实问答样本（每事实一条，共 22 条）：query 在 5 类难度中轮流取用，reference=事实陈述原文。
  - 检索上下文用完整管线（BM25 + 向量 + RRF + Reranker，top-5），答案由主 LLM 基于上下文生成。

依赖：
  - ragas>=0.3.1（本机 langchain-community 0.4.x 移除了 Google VertexAI，ragas 顶部会无条件 import
    该模块导致 ImportError；这里在 import ragas 前注入两个空占位模块绕开，评测只用 ChatOpenAI 走 DeepSeek）。
  - BGE embedding / reranker 模型已缓存（离线用 HF_HUB_OFFLINE=1）。

输出：backend/output/ragas_result.md
"""
from __future__ import annotations

import asyncio
import logging
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
log = logging.getLogger("eval-ragas")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

OUTPUT_PATH = BACKEND_DIR / "output" / "ragas_result.md"
TOP_K = 5


# ── ragas import 兼容垫片 ───────────────────────────────────────────────
# ragas 0.3.1 顶层会无条件 `from langchain_community.chat_models.vertexai import ChatVertexAI`
# 与 `from langchain_community.llms import VertexAI`；langchain-community 0.4.x 已移除这两个
# 模块。此处注入空占位模块，仅为了让 ragas 能 import，评测实际不使用 VertexAI。
def _shim_missing_modules() -> None:
    class _Dummy:  # 占位类，不会被实例化
        def __init__(self, *a, **k):
            pass

    for name, attrs in (
        ("langchain_community.chat_models.vertexai", {"ChatVertexAI": _Dummy}),
        ("langchain_community.llms", {"VertexAI": _Dummy}),
    ):
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod


_shim_missing_modules()

from ragas import evaluate, EvaluationDataset, SingleTurnSample  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.embeddings.base import BaseRagasEmbeddings  # noqa: E402
from ragas.metrics import (  # noqa: E402
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)
from langchain_core.messages import SystemMessage, HumanMessage  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.embedding import embedding_service  # noqa: E402
from scripts.eval_data import FACTS  # noqa: E402


class BgeRagasEmbeddings(BaseRagasEmbeddings):
    """把应用内 BGE embedding 服务适配为 ragas 需要的 embedding 接口。"""

    def embed_query(self, text: str):
        return embedding_service.embed_query(text)

    def embed_documents(self, texts: list[str]):
        return embedding_service.embed_texts(texts)

    async def aembed_query(self, text: str):
        return await asyncio.to_thread(embedding_service.embed_query, text)

    async def aembed_documents(self, texts: list[str]):
        return await asyncio.to_thread(embedding_service.embed_texts, texts)


def _build_judge() -> LangchainLLMWrapper:
    api_key = settings.judge_api_key or settings.openai_api_key
    if not api_key or "placeholder" in api_key or "your-key" in api_key:
        raise SystemExit("未配置可用的 judge API Key（JUDGE_API_KEY / OPENAI_API_KEY）")
    llm = ChatOpenAI(
        model=settings.judge_model,
        base_url=settings.judge_base_url,
        api_key=api_key,
        temperature=0.0,
        max_tokens=1024,
    )
    return LangchainLLMWrapper(llm)


def _build_answer_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        temperature=0.1,
        max_tokens=1024,
    )


async def _generate_answer(llm: ChatOpenAI, question: str, contexts: list[str]) -> str:
    ctx = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    messages = [
        SystemMessage(content="你是企业知识助手，只依据给定资料简洁、准确地回答用户问题，不要编造。"),
        HumanMessage(content=f"资料：\n{ctx}\n\n问题：{question}\n\n回答："),
    ]
    resp = await llm.ainvoke(messages)
    return (resp.content or "").strip()


async def build_samples() -> list[SingleTurnSample]:
    """对每个事实检索上下文 + 生成答案，组装为 ragas SingleTurnSample。

    每事实取 2 类难例（加权难例），共 44 条：偶数事实取（同义改写、反向否定），
    奇数事实取（跨语言、多主题干扰），避免只用基线直配导致 context_precision/recall 饱和。
    """
    from app.database import AsyncSessionLocal
    from app.services.retriever import HybridRetriever

    answer_llm = _build_answer_llm()
    retriever = HybridRetriever(reranker_enabled=True)
    samples: list[SingleTurnSample] = []

    async with AsyncSessionLocal() as db:
        for i, fact in enumerate(FACTS, 1):
            types = ("q_para", "q_neg") if i % 2 == 0 else ("q_cross", "q_distract")
            for qt in types:
                question = fact[qt]
                emb = await asyncio.to_thread(embedding_service.embed_query, question)
                results = await retriever.hybrid_search(question, emb, db, top_k=TOP_K)
                contexts = [(r.content or "") for r in results]
                if not contexts:
                    log.warning(f"样本（{question}）未检索到上下文，跳过")
                    continue
                answer = await _generate_answer(answer_llm, question, contexts)
                samples.append(SingleTurnSample(
                    user_input=question,
                    retrieved_contexts=contexts,
                    response=answer,
                    reference=fact["statement"],
                ))
                log.info(f"样本 {len(samples)} 就绪：{question}")

    return samples


def _metric_name(col: str) -> str:
    return {
        "faithfulness": "faithfulness",
        "answer_relevancy": "answer_relevancy",
        "context_precision": "context_precision",
        "context_recall": "context_recall",
    }.get(col, col)


def build_markdown(scores: dict[str, float], n_samples: int) -> str:
    lines = []
    lines.append("# RAGAS 生成质量评测")
    lines.append("")
    lines.append(f"- 评测样本：{n_samples} 条真实问答（每事实取 2 类难例，reference=事实陈述原文）")
    lines.append("- 检索上下文：完整管线（BM25 + 向量 + RRF + Reranker，top-5）")
    lines.append("- 答案生成：主 LLM（DeepSeek）；评分：LLM-as-judge（复用 judge 字段）")
    lines.append("")
    lines.append("| 指标 | 分数 | 说明 |")
    lines.append("|---|---|---|")
    lines.append(f"| faithfulness | {scores.get('faithfulness', 0):.4f} | 回答是否忠于检索上下文（无编造） |")
    lines.append(f"| answer_relevancy | {scores.get('answer_relevancy', 0):.4f} | 回答与问题的相关程度 |")
    lines.append(f"| context_precision | {scores.get('context_precision', 0):.4f} | 相关上下文在检索结果中的排序精度 |")
    lines.append(f"| context_recall | {scores.get('context_recall', 0):.4f} | 检索结果覆盖参考答案信息的比例 |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    judge = _build_judge()
    embeddings = BgeRagasEmbeddings()

    log.info("构建 RAGAS 评测样本（检索 + 生成答案）...")
    samples = asyncio.run(build_samples())
    if len(samples) < 10:
        raise SystemExit(f"有效样本不足（{len(samples)} 条），请检查知识库与 LLM 配置")
    log.info(f"共 {len(samples)} 条样本，开始 RAGAS 评测...")

    dataset = EvaluationDataset(samples=samples)
    metrics = [
        Faithfulness(llm=judge),
        AnswerRelevancy(llm=judge, embeddings=embeddings),
        ContextPrecision(llm=judge),
        ContextRecall(llm=judge),
    ]
    result = evaluate(dataset, metrics=metrics, show_progress=False)
    df = result.to_pandas()

    scores: dict[str, float] = {}
    for col in df.columns:
        if col in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            scores[col] = float(df[col].mean())

    markdown = build_markdown(scores, len(samples))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(markdown)
    log.info(f"结果已写入 {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
