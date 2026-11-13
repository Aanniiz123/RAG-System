import logging
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import AsyncSession

from src.scheme.document import DocumentUploadResponse

from src.database import get_db
from src.models.document import Document
from src.services.document import chunk_pages, extract_pages


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
MAX_FILE_BYTES = 15 * 1024 * 1024


@router.post("", response_model = DocumentUploadResponse )
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    strategy: Literal["fixed", "recursive"] = Form(...),
    chunk_size: int = Form(200),
    chunk_overlap: int = Form(30),
    db: AsyncSession = Depends(get_db),
):
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()

    if suffix not in {".pdf", ".txt"}:
        raise HTTPException(415, "Only PDF and TXT files are supported")

    if chunk_size < 1 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise HTTPException(422, "Invalid chunk size or overlap")

    embedder = request.app.state.embedder
    if chunk_size > embedder.max_seq_length - 2:
        raise HTTPException(
            422,
            f"chunk_size must be at most {embedder.max_seq_length - 2} "
            "for the configured embedding model",
        )

    content = await file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "File is too large")

    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(422, "The uploaded file does not look like a PDF")

    try:
        pages = await run_in_threadpool(extract_pages, suffix, content)
        chunks = await run_in_threadpool(
            chunk_pages,
            pages,
            embedder.tokenizer,
            strategy,
            chunk_size,
            chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    if not chunks:
        raise HTTPException(422, "No extractable text was found")

    document_id = str(uuid.uuid4())
    document = Document(
        id=document_id,
        filename=filename,
        status="processing",
        chunk_strategy=strategy,
        embedding_model=request.app.state.embedding_model_name,
    )
    db.add(document)
    await db.commit()

    try:
        texts = [chunk["text"] for chunk in chunks]
        vectors = await run_in_threadpool(
            embedder.encode,
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector.tolist(),
                payload={
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": index,
                    "page_number": chunk["page_number"],
                    "chunk_strategy": strategy,
                    "text": chunk["text"],
                },
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]

        await run_in_threadpool(
            request.app.state.qdrant.upsert,
            collection_name=request.app.state.collection_name,
            points=points,
            wait=True,
        )

        document.status = "completed"
        document.chunk_count = len(chunks)
        await db.commit()

    except Exception as exc:
        logger.exception("Document ingestion failed: %s", document_id)
        document.status = "failed"
        document.error = str(exc)[:2000]
        await db.commit()
        raise HTTPException(500, "Document ingestion failed") from exc

    return {
        "document_id": document_id,
        "status": document.status,
        "chunk_count": document.chunk_count,
        "strategy": strategy,
    }