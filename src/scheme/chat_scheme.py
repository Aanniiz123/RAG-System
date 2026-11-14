from datetime import date, time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field


class ConversationIdResponse(BaseModel):
    conversation_id: UUID


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    conversation_id: UUID
    answer: str
    booking_status: Literal[
        "collecting",
        "awaiting_confirmation",
        "confirmed",
        "cancelled",
    ] | None = None


class BookingDetails(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    interview_date: date
    interview_time: time


class BookingDraft(BaseModel):
    booking_id: UUID = Field(default_factory=uuid4)
    name: str | None = None
    email: str | None = None
    date: str | None = None
    time: str | None = None
    status: Literal["collecting", "awaiting_confirmation"] = "collecting"
