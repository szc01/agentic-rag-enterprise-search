"""LangGraph StateGraph：四 Agent 多步检索编排图"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from app.services.agents.types import GraphState, SubQuery
from app.services.agents.planner import planner_agent
from app.services.agents.retrieval import retrieval_agent
from app.services.agents.critic import critic_agent
from app.services.agents.synthesizer import synthesizer_agent

logger = logging.getLogger(__name__)

# 最大自循环次数（Critic 每轮 +1，达到上限强制去 Synthesizer）
MAX_ITERATIONS = 3


# ── Node 函数（每个 Agent 对应一个 Node）──────────

async def planner_node(state: GraphState) -> dict:
    """Node 1: Planner — 问题分解"""
    logger.info("=== [Planner] 开始 ===")
    sub_queries = await planner_agent.plan(
        state["question"],
        history=state.get("history", []),
    )
    return {
        "plan": sub_queries,
        "current_query_index": 0,
        "retrieved_chunks": [],
        "iterations": 0,
    }


async def retrieval_node(state: GraphState, config: RunnableConfig) -> dict:
    """Node 2: Retrieval — 执行子查询检索

    db 会话通过 graph 的 configurable 注入（避免把活动连接塞进 state 被 checkpoint）。
    """
    logger.info("=== [Retrieval] 开始 ===")
    db = None
    if config and config.get("configurable"):
        db = config["configurable"].get("db")
    if not db:
        logger.warning("Retrieval: 未注入 db session，跳过实际检索")
        return {"current_query_index": state.get("current_query_index", 0) + 1}

    return await retrieval_agent.retrieve(state, db)


async def critic_node(state: GraphState) -> dict:
    """Node 3: Critic — 信息充分性审查（不充分时把建议查询追加进 plan）"""
    logger.info("=== [Critic] 开始 ===")
    result = await critic_agent.critique(state)

    # 每次经过 Critic 迭代计数 +1
    new_iterations = state.get("iterations", 0) + 1
    result["iterations"] = new_iterations

    verdict = result["critic_verdict"]

    # 防死循环：达到上限强制标记充分（critique 内部已兜底，这里双保险）
    max_iterations = state.get("max_iterations", MAX_ITERATIONS)
    if new_iterations >= max_iterations:
        verdict.sufficient = True
        verdict.reasoning += f" [强制终止：已达 {max_iterations} 轮]"

    # 不充分且 Critic 给出建议 → 追加到 plan，让 retrieval 再跑一轮
    if not verdict.sufficient and verdict.suggested_queries:
        plan = list(state.get("plan", []))
        extra = [SubQuery(q, "Critic 建议补充") for q in verdict.suggested_queries[:2]]
        if extra:
            result["plan"] = plan + extra
            logger.info(f"→ 追加 {len(extra)} 个补充子查询: {[s.query for s in extra]}")

    return result


async def synthesizer_node(state: GraphState) -> dict:
    """Node 4: Synthesizer — 综合生成答案（报告模式下输出结构化调研报告）"""
    logger.info("=== [Synthesizer] 开始 ===")
    if state.get("report_mode"):
        logger.info("Synthesizer: 报告模式")
        return await synthesizer_agent.synthesize_report(state)
    return await synthesizer_agent.synthesize(state)


# ── 条件边函数 ────────────────────────────────

def should_continue_retrieval(
    state: GraphState,
) -> Literal["retrieval", "synthesize"]:
    """
    Critic 后的条件分支：
      - sufficient=True → 去 Synthesizer
      - 未充分但有未执行的子查询（含 Critic 建议补充的）→ 回 Retrieval
      - 达到迭代上限 → 强制去 Synthesizer

    注意：条件边只做路由，不能更新 state；plan 的扩展在 critic_node 内完成。
    """
    verdict = state.get("critic_verdict")
    iterations = state.get("iterations", 0)
    plan = state.get("plan", [])
    current_idx = state.get("current_query_index", 0)
    max_iterations = state.get("max_iterations", MAX_ITERATIONS)

    if verdict and verdict.sufficient:
        logger.info(f"→ Critic 判定信息充分 (conf={verdict.confidence:.2f})，去 Synthesizer")
        return "synthesize"

    if iterations >= max_iterations:
        logger.warning(f"→ 已达最大迭代次数 {max_iterations}，强制去 Synthesizer")
        return "synthesize"

    if current_idx < len(plan):
        logger.info(f"→ 信息不充分，继续执行第 {current_idx+1} 个子查询")
        return "retrieval"

    logger.info("→ 无更多可执行操作，去 Synthesizer")
    return "synthesize"


# ── 构建图 ────────────────────────────────────

def build_graph() -> StateGraph:
    """
    构建 Agentic RAG 多步检索状态机。

    图结构：

        start → [Planner] → [Retrieval] → [Critic]
                                        ↓
                              sufficient? ─否→ [Retrieval] (循环)
                                        │是
                                        ↓
                                  [Synthesizer] → end

    防死循环机制：
      - iterations 计数器，每轮 +1
      - MAX_ITERATIONS=3 上限强制跳出
      - Critic 的 self-loop 有条件边保护
    """
    graph = StateGraph(GraphState)

    # 注册 Node
    graph.add_node("planner", planner_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("critic", critic_node)
    graph.add_node("synthesizer", synthesizer_node)

    # 设置入口
    graph.set_entry_point("planner")

    # 设置边
    graph.add_edge("planner", "retrieval")
    graph.add_conditional_edges(
        "retrieval",
        # 所有子查询都执行完后自动去 Critic
        lambda state: (
            "critic"
            if state.get("current_query_index", 0) >= len(state.get("plan", []))
            else "retrieval"
        ),
        {"retrieval": "retrieval", "critic": "critic"},
    )
    graph.add_conditional_edges(
        "critic",
        should_continue_retrieval,
        {"retrieval": "retrieval", "synthesize": "synthesizer"},
    )
    graph.add_edge("synthesizer", END)

    logger.info("Agentic RAG StateGraph 构建完成")
    return graph


# 编译后的可执行图（单例）
_compiled_graph = None


def _build_checkpointer():
    """构建 LangGraph checkpointer 用于会话状态持久化。

    优先使用 Postgres（需安装 langgraph-checkpoint-postgres，且配置了
    checkpoint_postgres_uri）；否则回退到内存 InMemorySaver（单进程内跨请求
    恢复会话，足以支撑本地部署的多轮问答）。
    """
    from app.config import settings

    uri = settings.checkpoint_postgres_uri
    if uri:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            saver = PostgresSaver.from_conn_string(uri)
            saver.setup()  # 幂等建 checkpoint 表
            logger.info("已启用 Postgres checkpointer（跨进程会话持久化）")
            return saver
        except Exception as e:  # 缺包 / 连不上库时优雅降级
            logger.warning(f"Postgres checkpointer 初始化失败，回退内存: {e}")

    from langgraph.checkpoint.memory import InMemorySaver
    logger.info("已启用内存 checkpointer（单进程内跨请求会话恢复）")
    return InMemorySaver()


def get_compiled_graph():
    """获取编译后的图实例（懒加载，带 checkpointer）"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph().compile(checkpointer=_build_checkpointer())
    return _compiled_graph


async def _load_session_history(thread_id: str) -> list[dict]:
    """从 checkpointer 恢复指定会话的 history（跨请求多轮指代消解）。"""
    graph = get_compiled_graph()
    try:
        snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        if snap and snap.values:
            return list(snap.values.get("history") or [])
    except Exception as e:
        logger.warning(f"从 checkpointer 恢复历史失败: {e}")
    return []


async def _save_session_turn(
    thread_id: str,
    history: list[dict],
    question: str,
    answer: str,
) -> None:
    """把本轮问答追加进 history 并写回 checkpointer，供下一轮恢复。"""
    graph = get_compiled_graph()
    try:
        updated = list(history or []) + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
        await graph.aupdate_state(
            {"configurable": {"thread_id": thread_id}},
            {"history": updated},
        )
    except Exception as e:
        logger.warning(f"写回 checkpointer 历史失败: {e}")


# ── 便捷执行函数 ──────────────────────────────

async def _invoke_graph(
    question: str,
    db,  # AsyncSession
    report_mode: bool = False,
    max_iterations: int = MAX_ITERATIONS,
    history: list[dict] | None = None,
    thread_id: str | None = None,
) -> tuple[dict, int]:
    """执行编排图，返回 (final_state, latency_ms)。

    thread_id 非空时启用会话持久化：未显式传 history 则从 checkpointer 恢复上一轮
    会话历史，并在本轮结束后把「用户提问 + 助手回答」写回，供下一轮跨请求恢复。
    db 会话仍走 configurable 注入（不把活动连接写进 checkpoint）。
    """
    import time
    start_time = time.time()

    graph = get_compiled_graph()

    # 跨请求恢复会话历史（指代消解）
    if history is None and thread_id:
        history = await _load_session_history(thread_id)
    history = history or []

    config = {"configurable": {"db": db}}
    if thread_id:
        config["configurable"]["thread_id"] = thread_id

    final_state = await graph.ainvoke(
        {
            "question": question,
            "history": history,
            "report_mode": report_mode,
            "max_iterations": max_iterations,
        },
        config=config,
    )

    # 把本轮问答写回 checkpointer
    if thread_id:
        await _save_session_turn(
            thread_id, history, question, final_state.get("answer", "")
        )

    latency_ms = int((time.time() - start_time) * 1000)
    return final_state, latency_ms


def _state_to_result(final_state: dict, latency_ms: int) -> dict:
    """把图最终 state 转成对外统一的查询结果字典。"""
    return {
        "answer": final_state.get("answer", ""),
        "citations": [
            {
                "chunk_id": c.chunk_id,
                "document_title": c.document_title,
                "section": c.section,
                "content_snippet": c.content_snippet,
            }
            for c in final_state.get("citations", [])
        ],
        "confidence_score": max(0.0, min(1.0, final_state.get("confidence_score", 0.0))),
        "latency_ms": latency_ms,
        "trace": {
            "iterations": final_state.get("iterations", 0),
            "sub_queries": [sq.query for sq in final_state.get("plan", [])],
            "chunks_retrieved": len(final_state.get("retrieved_chunks", [])),
            "critic_verdict": (
                final_state.get("critic_verdict").__dict__
                if final_state.get("critic_verdict") else None
            ),
        },
    }


async def run_agentic_query(
    question: str,
    db,  # AsyncSession
    history: list[dict] | None = None,
    thread_id: str | None = None,
) -> dict:
    """
    一站式执行 Agentic RAG 查询。

    Args:
        question: 用户问题
        db: 数据库会话
        history: 多轮对话历史 [{"role", "content"}]
        thread_id: 会话 ID（非空时启用 checkpointer 跨请求恢复历史）

    Returns:
        包含 answer / citations / confidence_score / trace 的字典
    """
    final_state, latency_ms = await _invoke_graph(
        question, db, history=history, thread_id=thread_id
    )
    result = _state_to_result(final_state, latency_ms)

    logger.info(
        f"Agentic 查询完成: {latency_ms}ms, "
        f"iterations={result['trace']['iterations']}, "
        f"chunks={result['trace']['chunks_retrieved']}, "
        f"conf={result['confidence_score']:.2f}"
    )

    return result


async def run_agentic_report(
    topic: str,
    depth: int,
    db,  # AsyncSession
) -> dict:
    """
    执行 Agentic 调研报告编排（Synthesizer 走报告模式）。

    Args:
        topic: 调研主题
        depth: 检索深度（迭代轮数，1-5）
        db: 数据库会话

    Returns:
        与 run_agentic_query 同构的字典，answer 为完整 Markdown 报告全文
    """
    max_iterations = max(1, min(int(depth), 5))
    final_state, latency_ms = await _invoke_graph(
        topic, db, report_mode=True, max_iterations=max_iterations
    )
    result = _state_to_result(final_state, latency_ms)

    logger.info(
        f"Agentic 报告生成完成: {latency_ms}ms, "
        f"iterations={result['trace']['iterations']}, "
        f"chunks={result['trace']['chunks_retrieved']}, "
        f"citations={len(result['citations'])}, "
        f"conf={result['confidence_score']:.2f}"
    )

    return result


async def run_agentic_query_stream(
    question: str,
    db,  # AsyncSession
    history: list[dict] | None = None,
    thread_id: str | None = None,
):
    """
    Agentic 查询的流式变体：编排逻辑与 build_graph() 完全一致，
    只是 Synthesizer 改用逐 token 流式产出，便于 SSE 推给前端。

    复用同一套 agent 单例（planner/retrieval/critic/synthesizer），
    不依赖 LangGraph 的 astream_events（1.x 已弃用，行为跨版本不稳）。

    Yields:
        {"type": "status", "stage": ..., ...}   —— 编排进度（planning/retrieval/critic/synthesizing）
        {"type": "token", "content": str}       —— Synthesizer 逐 token 文本
        {"type": "result", "answer":..., "citations":..., "confidence_score":..., "latency_ms":..., "trace":...}
    """
    import time
    start_time = time.time()

    # 跨请求恢复会话历史（与 _invoke_graph 保持一致）
    if history is None and thread_id:
        history = await _load_session_history(thread_id)
    history = history or []

    # ── Planner ──────────────────────────────
    yield {"type": "status", "stage": "planning"}
    plan = await planner_agent.plan(question, history=history)
    yield {
        "type": "status",
        "stage": "planned",
        "sub_queries": [sq.query for sq in plan],
    }

    retrieved_chunks: list[dict] = []
    critic_verdict = None
    iterations = 0
    current_idx = 0
    max_iterations = MAX_ITERATIONS

    while True:
        # ── Retrieval：执行 plan 里所有（含 Critic 补充的）子查询 ──
        while current_idx < len(plan):
            sub_query = plan[current_idx]
            yield {
                "type": "status",
                "stage": "retrieval",
                "current_query_index": current_idx,
                "total_sub_queries": len(plan),
                "sub_query": sub_query.query,
            }
            state: GraphState = {
                "question": question,
                "plan": plan,
                "current_query_index": current_idx,
                "retrieved_chunks": retrieved_chunks,
                "critic_verdict": critic_verdict,
                "iterations": iterations,
                "max_iterations": max_iterations,
            }
            update = await retrieval_agent.retrieve(state, db)
            retrieved_chunks = update.get("retrieved_chunks", retrieved_chunks)
            current_idx = update.get("current_query_index", current_idx + 1)
            yield {
                "type": "status",
                "stage": "retrieved",
                "chunks_retrieved": len(retrieved_chunks),
            }

        # ── Critic ────────────────────────────
        yield {"type": "status", "stage": "critic"}
        state = {
            "question": question,
            "plan": plan,
            "current_query_index": current_idx,
            "retrieved_chunks": retrieved_chunks,
            "critic_verdict": critic_verdict,
            "iterations": iterations,
            "max_iterations": max_iterations,
        }
        critic_result = await critic_agent.critique(state)
        critic_verdict = critic_result["critic_verdict"]
        iterations += 1

        # 防死循环（与 critic_node / should_continue_retrieval 一致）
        if iterations >= max_iterations and not critic_verdict.sufficient:
            critic_verdict.sufficient = True
            critic_verdict.reasoning += f" [强制终止：已达 {max_iterations} 轮]"

        if not critic_verdict.sufficient and critic_verdict.suggested_queries:
            extra = [
                SubQuery(q, "Critic 建议补充")
                for q in critic_verdict.suggested_queries[:2]
            ]
            plan = plan + extra

        yield {
            "type": "status",
            "stage": "critiqued",
            "sufficient": critic_verdict.sufficient,
            "iterations": iterations,
        }

        if critic_verdict.sufficient or iterations >= max_iterations:
            break
        if current_idx < len(plan):
            continue
        break

    # ── Synthesizer（流式）───────────────────
    yield {"type": "status", "stage": "synthesizing"}
    final_state = {
        "question": question,
        "history": history,
        "plan": plan,
        "current_query_index": current_idx,
        "retrieved_chunks": retrieved_chunks,
        "critic_verdict": critic_verdict,
        "iterations": iterations,
        "max_iterations": max_iterations,
    }
    synth_result = None
    async for kind, payload in synthesizer_agent.synthesize_stream(final_state):
        if kind == "token":
            yield {"type": "token", "content": payload}
        else:
            synth_result = payload

    latency_ms = int((time.time() - start_time) * 1000)

    # 把本轮问答写回 checkpointer
    if thread_id:
        await _save_session_turn(
            thread_id, history, question, synth_result.get("answer", "")
        )

    yield {
        "type": "result",
        "answer": synth_result["answer"],
        "citations": [
            {
                "chunk_id": c.chunk_id,
                "document_title": c.document_title,
                "section": c.section,
                "content_snippet": c.content_snippet,
            }
            for c in synth_result["citations"]
        ],
        "confidence_score": max(0.0, min(1.0, synth_result["confidence_score"])),
        "latency_ms": latency_ms,
        "trace": {
            "iterations": iterations,
            "sub_queries": [sq.query for sq in plan],
            "chunks_retrieved": len(retrieved_chunks),
            "critic_verdict": (
                critic_verdict.__dict__ if critic_verdict else None
            ),
        },
    }
