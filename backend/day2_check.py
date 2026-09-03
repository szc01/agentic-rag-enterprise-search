"""Day 2 验收: agentic graph 全链路（DeepSeek + 混合检索 + 引用）"""
import asyncio, sys, time
sys.path.insert(0, r"D:/agentic-rag-system/backend")

async def main():
    from app.database import AsyncSessionLocal
    from app.graph import run_agentic_query

    q = "How does chunking strategy affect retrieval quality?"
    t0 = time.time()
    async with AsyncSessionLocal() as db:
        result = await run_agentic_query(q, db)
    dt = time.time() - t0

    print(f"[Q] {q}")
    print(f"[耗时] {dt:.1f}s")
    print(f"[答案] {(result['answer'] or '')[:300]}")
    print(f"[引用数] {len(result.get('citations', []))}")
    for c in result.get('citations', [])[:3]:
        print(f"  - {c.get('document_title','?')} | {str(c.get('content_snippet',''))[:60]}")
    print(f"[置信度] {result.get('confidence_score')}")
    tr = result.get('trace', {})
    print(f"[trace] sub_queries={tr.get('sub_queries')}, chunks={tr.get('chunks_retrieved')}, iterations={tr.get('iterations')}, critic={tr.get('critic_verdict')}")
    # 断言
    assert result['answer'], "答案为空"
    assert result.get('citations'), "无引用"
    assert tr.get('chunks_retrieved', 0) > 0, "未检索到 chunk"
    print("=== DAY2 E2E PASSED ===")

asyncio.run(main())
