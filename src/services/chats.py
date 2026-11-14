import json
from datetime import date, datetime, time
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from pydantic import EmailStr, Field, ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from core.config import setting
from core.llm import GroqLLM
from src.models.chat import Booking
from src.scheme.chat_scheme import (
    BookingDetails,
    ChatRequest,
    ChatResponse,
    BookingDraft,
)
from src.services.retrieval import QdrantRetriever



class ChatService:
    def __init__(
        self,
        redis: Redis,
        llm: GroqLLM,
        retriever: QdrantRetriever) -> None:

        self._redis = redis
        self._llm = llm
        self._retriever = retriever
        self._ttl_seconds = 60 * 60 * 24
        self._history_limit = 40

    async def reply(
        self,
        request: ChatRequest,
        db: AsyncSession) -> ChatResponse:

        conversation_id = request.conversation_id or uuid4()
        history_key = f"chat:{conversation_id}:messages"
        draft_key = f"chat:{conversation_id}:booking"

        history = await self._load_history(history_key)
        await self._append_message(history_key, "user", request.message)

        raw_draft = await self._redis.get(draft_key)
        draft = BookingDraft.model_validate_json(raw_draft) if raw_draft else None

        if draft and draft.status == "awaiting_confirmation":
            answer, status = await self._confirm_booking(
                request.message,
                conversation_id,
                draft_key,
                draft,
                db,
            )
            return await self._finish(
                history_key, conversation_id, answer, status
            )

        extraction = await self._llm.extract_booking(
            history=history,
            message=request.message,
            draft=draft.model_dump(exclude={"booking_id", "status"})
            if draft
            else None,
        )

        if extraction.intent == "booking":
            draft = draft or BookingDraft()
            answer, status = await self._update_booking_draft(draft_key, draft, extraction)
            return await self._finish(history_key, conversation_id, answer, status)

        standalone_query = await self._llm.rewrite_query(
            history,
            request.message,
        )
        chunks = await self._retriever.retrieve(standalone_query)
        answer = await self._llm.answer(
            history=history,
            question=request.message,
            context="\n\n---\n\n".join(chunks),
        )
        return await self._finish(history_key, conversation_id, answer, None)

    async def _update_booking_draft(
        self,
        draft_key: str,
        draft: BookingDraft,
        extraction: object,
    ) -> tuple[str, Literal["collecting", "awaiting_confirmation"]]:
        values = draft.model_dump()
        fields = extraction.model_dump(exclude={"intent"})

        for field in ("name", "email"):
            value = fields[field]
            if isinstance(value, str) and value.strip():
                values[field] = value.strip()

        for field, parser in (
            ("date", date.fromisoformat),
            ("time", time.fromisoformat),
        ):
            value = fields[field]
            if isinstance(value, str) and value.strip():
                try:
                    parsed = parser(value.strip())
                except ValueError:
                    label = "YYYY-MM-DD" if field == "date" else "HH:MM"
                    return (
                        f"Please provide the interview {field} in {label} format.",
                        "collecting",
                    )
                if field == "time" and parsed.tzinfo is not None:
                    return (
                        "Please provide the interview time in the business "
                        "timezone, without a UTC offset.",
                        "collecting",
                    )
                values[field] = parsed.isoformat()

        draft = BookingDraft.model_validate(values)
        missing = [
            field
            for field in ("name", "email", "date", "time")
            if not getattr(draft, field)
        ]

        if missing:
            await self._save_draft(draft_key, draft)
            labels = {
                "name": "your name",
                "email": "your email address",
                "date": "the interview date",
                "time": "the interview time",
            }
            needed = ", ".join(labels[field] for field in missing)
            return f"I still need {needed} to continue the booking.", "collecting"

        interview_date = date.fromisoformat(draft.date or "")
        today = datetime.now().date()
        if interview_date < today:
            await self._save_draft(draft_key, draft)
            return (
                "That date is in the past. Please provide a future interview date.",
                "collecting",
            )

        try:
            details = BookingDetails(
                name=draft.name or "",
                email=draft.email or "",
                interview_date=interview_date,
                interview_time=time.fromisoformat(draft.time or ""),
            )
        except ValidationError as exc:
            if any(error["loc"] == ("email",) for error in exc.errors()):
                await self._save_draft(draft_key, draft)
                return (
                    "That email address does not look valid. "
                    "Please provide it again.",
                    "collecting",
                )
            raise

        draft.status = "awaiting_confirmation"
        await self._save_draft(draft_key, draft)
        
        return (
            f"Please confirm this interview booking: {details.name}, "
            f"{details.email}, {details.interview_date.isoformat()} at "
            f"{details.interview_time.strftime('%H:%M')}. "
            "Reply 'yes' to save it or 'no' to cancel.",
            "awaiting_confirmation",
        )

    async def _confirm_booking(
        self,
        message: str,
        conversation_id: UUID,
        draft_key: str,
        draft: BookingDraft,
        db: AsyncSession,
    ) -> tuple[
        str,
        Literal["confirmed", "cancelled", "awaiting_confirmation"],
    ]:
        answer = message.casefold().strip().strip(".!?")

        if answer in {"no", "cancel", "cancel booking"}:
            await self._redis.delete(draft_key)
            return "The interview booking was cancelled.", "cancelled"

        if answer not in {"yes", "confirm", "confirm booking"}:
            return (
                "Please reply 'yes' to save the booking or 'no' to cancel it.",
                "awaiting_confirmation",
            )

        details = BookingDetails(
            name=draft.name or "",
            email=draft.email or "",
            interview_date=date.fromisoformat(draft.date or ""),
            interview_time=time.fromisoformat(draft.time or ""),
        )

        booking_id = str(draft.booking_id)
        existing = await db.get(Booking, booking_id)
        if existing is None:
            db.add(
                Booking(
                    id=booking_id,
                    conversation_id=str(conversation_id),
                    name=details.name,
                    email=str(details.email),
                    interview_date=details.interview_date,
                    interview_time=details.interview_time,
                )
            )
            await db.commit()

        await self._redis.delete(draft_key)
        return "Your interview booking has been saved.", "confirmed"

    async def _load_history(self, key: str) -> list[dict[str, str]]:
        entries = await self._redis.lrange(key, -12, -1)
        return [json.loads(entry) for entry in entries]

    async def _append_message(
        self,
        key: str,
        role: Literal["user", "assistant"],
        content: str,
    ) -> None:
        await self._redis.rpush(
            key,
            json.dumps({"role": role, "content": content}),
        )
        await self._redis.ltrim(key, -self._history_limit, -1)
        await self._redis.expire(key, self._ttl_seconds)

    async def _save_draft(self, key: str, draft: BookingDraft) -> None:
        await self._redis.set(
            key,
            draft.model_dump_json(),
            ex=self._ttl_seconds,
        )

    async def _finish(
        self,
        history_key: str,
        conversation_id: UUID,
        answer: str,
        booking_status: Literal[
            "collecting",
            "awaiting_confirmation",
            "confirmed",
            "cancelled",
        ] | None,
    ) -> ChatResponse:
        await self._append_message(history_key, "assistant", answer)
        return ChatResponse(
            conversation_id=conversation_id,
            answer=answer,
            booking_status=booking_status,
        )