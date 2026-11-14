import asyncio
from typing import Any

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


class QdrantRetriever:
    def __init__(
        self,
        client: QdrantClient,
        embedder: SentenceTransformer,
        collection_name: str,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._collection_name = collection_name

    async def retrieve(self, query: str, limit: int = 5) -> list[str]:
        vector = await asyncio.to_thread(
            self._embedder.encode,
            query,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        result = await asyncio.to_thread(
            self._client.query_points,
            collection_name=self._collection_name,
            query=vector.tolist(),
            limit=limit,
            with_payload=True,
        )

        chunks: list[str] = []
        for point in result.points:
            payload: dict[str, Any] = point.payload or {}
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                continue

            filename = payload.get("filename", "unknown file")
            page_number = payload.get("page_number", "unknown")
            chunks.append(
                f"Source: {filename}, page {page_number}\n{text.strip()}"
            )

        return chunks