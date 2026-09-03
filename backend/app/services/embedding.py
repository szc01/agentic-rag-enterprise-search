"""向量化服务：BGE 本地 Embedding 模型"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    BGE-large-zh-v1.5 本地 Embedding 服务。
    
    特点：
      - 模型本地运行，不消耗 API 费用
      - 首次调用时自动下载模型（~1.2 GB）
      - 支持批量嵌入，内部做批次切分避免 OOM
      - Lazy load：首次调用 embed_texts() 时才加载模型
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cpu",
        batch_size: int = 32,
        max_seq_length: int = 512,
    ):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self._model = None
        self._tokenizer = None
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy load：首次使用时加载模型"""
        if self._loaded:
            return

        logger.info(f"正在加载 Embedding 模型: {self.model_name} ...")
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._tokenizer = self._model.tokenizer
        self._loaded = True
        logger.info("Embedding 模型加载完成")

    def embed_texts(
        self,
        texts: list[str],
        normalize: bool = True,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """
        批量文本向量化。
        
        Args:
            texts: 文本列表（建议单条 < 512 字符，超长会被截断）
            normalize: 是否 L2 归一化（余弦相似度需要）
            show_progress: 是否显示进度条
            
        Returns:
            向量列表，每个向量是 float 列表
        """
        self._ensure_loaded()

        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        # 分批处理，避免 OOM
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            # 截断过长文本
            truncated = [t[:self.max_seq_length * 2] for t in batch]

            embeddings = self._model.encode(
                truncated,
                normalize_embeddings=normalize,
                show_progress_bar=show_progress and len(texts) > self.batch_size,
                batch_size=len(batch),
            )

            for emb in embeddings:
                all_embeddings.append(emb.tolist())

        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """单个查询向量化（便捷方法）"""
        results = self.embed_texts([query])
        return results[0] if results else []

    @property
    def dimension(self) -> int:
        """向量维度"""
        self._ensure_loaded()
        return self._model.get_sentence_embedding_dimension()


# 全局单例（lazy init）
embedding_service = EmbeddingService()
