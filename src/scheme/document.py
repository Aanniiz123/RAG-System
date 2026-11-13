from typing import Literal

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: Literal["completed"]
    chunk_count: int
    strategy: Literal["fixed", "recursive"]