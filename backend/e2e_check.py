"""Day 1 验收:真实 query -> BGE 向量化 -> pgvector 检索"""
import asyncio, sys
sys.path.insert(0, r"D:/agentic-rag-system/backend")

async def main():
    import asyncpg
    from app.services.embedding import embedding_service

    q = "What is a good chunking strategy?"
    qvec = embedding_service.embed_query(q)
    print(f"[Embed] query='{q}' -> dim={len(qvec)}")

    conn = await asyncpg.connect("postgresql://rag_user:rag_pass@localhost:5432/rag_db")
    vec_str = "[" + ",".join(f"{x:.6f}" for x in qvec) + "]"
    rows = await conn.fetch(
        "SELECT chunk_index, embedding <=> $1::vector AS dist, left(content, 70) AS preview "
        "FROM chunks ORDER BY embedding <=> $1::vector LIMIT 3", vec_str)
    for r in rows:
        print(f"  [top] dist={r['dist']:.4f} | {r['preview']}")
    assert rows[0]['chunk_index'] == 2, "预期最相关的是 chunk 2 (chunking strategy)"
    print("=== E2E CHECK PASSED ===")
    await conn.close()

asyncio.run(main())
