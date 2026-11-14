import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sentence_transformers import SentenceTransformer

from core.config import setting
from core.llm import GroqLLM
from src.router.chat import router as chat_router
from src.router.document import router as document_router
from src.services.chats import ChatService
from src.services.retrieval import QdrantRetriever

logger = logging.getLogger(__name__)


def _load_embedder() -> SentenceTransformer:
    return SentenceTransformer(
        setting.EMBEDDING_MODEL,
        device=setting.EMBEDDING_DEVICE,
    )


def _ensure_collection(
    client: QdrantClient,
    name: str,
    vector_size: int,
) -> None:
    if client.collection_exists(name):
        return

    try:
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )
    except UnexpectedResponse as exc:
        # Another app instance may have created the collection concurrently.
        if not client.collection_exists(name):
            raise
        logger.info("Collection %s was created concurrently: %s", name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    qdrant = QdrantClient(url=setting.QDRANT_URL)
    redis_client: Redis | None = None
    llm: GroqLLM | None = None

    try:
        redis_client = Redis.from_url(
            setting.REDIS_URL,
            decode_responses=True,
        )
        llm = GroqLLM()

        await redis_client.ping()

        # Load the embedding model and initialize Qdrant before accepting requests.
        embedder = await asyncio.to_thread(_load_embedder)
        vector_size = embedder.get_embedding_dimension()

        await asyncio.to_thread(
            _ensure_collection,
            qdrant,
            setting.QDRANT_COLLECTION,
            vector_size,
        )

        app.state.embedder = embedder
        app.state.embedding_model_name = setting.EMBEDDING_MODEL
        app.state.collection_name = setting.QDRANT_COLLECTION
        app.state.qdrant = qdrant
        app.state.redis = redis_client
        app.state.llm = llm
        app.state.chat_service = ChatService(
            redis=redis_client,
            llm=llm,
            retriever=QdrantRetriever(
                client=qdrant,
                embedder=embedder,
                collection_name=setting.QDRANT_COLLECTION,
            ),
        )

        yield
    finally:
        try:
            if llm is not None:
                await llm.close()
        finally:
            try:
                if redis_client is not None:
                    await redis_client.aclose()
            finally:
                qdrant.close()


app = FastAPI(lifespan=lifespan)
app.include_router(document_router)
app.include_router(chat_router)


@app.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    try:
        await asyncio.to_thread(request.app.state.qdrant.get_collections)
        await request.app.state.redis.ping()
    except (UnexpectedResponse, RedisError) as exc:
        logger.warning("Health check failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="A required service is unavailable",
        ) from exc

    return {"status": "ok"}