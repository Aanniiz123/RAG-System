import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from sentence_transformers import SentenceTransformer

from core.config import settings
from src.router.document import router as document_router

logger = logging.getLogger(__name__)


def _load_embedder() -> SentenceTransformer:
    return SentenceTransformer(
        settings.EMBEDDING_MODEL,
        device=settings.EMBEDDING_DEVICE,
    )


def _ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
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
        if not client.collection_exists(name):
            raise
        logger.info("Collection %s was created concurrently: %s", name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    qdrant = QdrantClient(url=settings.QDRANT_URL)
    try:
        # Heavy sync work off the event loop
        embedder = await asyncio.to_thread(_load_embedder)
        vector_size = embedder.get_embedding_dimension()

        await asyncio.to_thread(
            _ensure_collection, qdrant, settings.QDRANT_COLLECTION, vector_size
        )

        app.state.embedder = embedder
        app.state.embedding_model_name = settings.EMBEDDING_MODEL
        app.state.collection_name = settings.QDRANT_COLLECTION
        app.state.qdrant = qdrant

        yield
    finally:
        qdrant.close()


app = FastAPI(lifespan=lifespan)
app.include_router(document_router)


@app.get("/health")
async def health_check(request: Request):
    try:
        await asyncio.to_thread(request.app.state.qdrant.get_collections)
    except Exception:
        raise HTTPException(status_code=503, detail="Qdrant unavailable")
    return {"status": "ok"}