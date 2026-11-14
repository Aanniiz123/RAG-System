from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.scheme.chat_scheme import ChatRequest, ChatResponse,ConversationIdResponse
from src.services.chats import ChatService
from uuid import uuid4

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    service: ChatService = request.app.state.chat_service
    return await service.reply(body, db)

@router.get("/conversation-id", response_model = ConversationIdResponse)
def generate_conversation_id() -> ConversationIdResponse :
    return ConversationIdResponse(conversation_id=uuid4())



