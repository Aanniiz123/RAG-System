from datetime import date, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


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