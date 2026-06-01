"""GET /api/v1/history — recent verification requests with their citations."""
from __future__ import annotations

from typing import (Annotated, TypeVar)
from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Select
from sqlmodel import select


from app.platform.db.models import Citation, SearchRequest
from app.platform.db.session import session_scope
from app.api.generated.models import (
    Citation as ApiCitation,
)
from app.api.generated.models import (
    HistoryItem,
    HistoryResponse,
    Verdict,
)

GenericType = TypeVar("GenericT")

async def _fetch_all(session: AsyncSession, select_query: Select[tuple[GenericType]]) -> list[GenericType]:
    return (await session.execute(select_query)).scalars().all()

router = APIRouter(tags=["history"])

@router.get("/api/v1/history", response_model=HistoryResponse)
async def list_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HistoryResponse:
    
    async with session_scope() as session:
        requests  = await _fetch_all(
            session,
            select(SearchRequest).order_by(SearchRequest.created_at.desc()).limit(limit)
        )
        if not requests:
            return HistoryResponse(items=[])

        ids = [r.id for r in requests]
        
        citations_by_request: dict[int, list[Citation]] = {rid: [] for rid in ids}
        citations = await _fetch_all(
            session,
            select(Citation).where(Citation.request_id.in_(ids))
        )
        for c in citations:
            citations_by_request[c.request_id].append(c)

    items = [
        HistoryItem(
            id=r.id,
            claim=r.claim,
            datetime=r.created_at,
            verdict=Verdict(r.verdict),
            citations=[
                ApiCitation(
                    url=c.url,
                    title=c.title,
                    passage=c.passage,
                    label=Verdict(c.label),
                    reasoning=c.reasoning,
                )
                for c in (citations_by_request[r.id] if r.id is not None else [])
            ],
        )
        for r in requests
    ]
    return HistoryResponse(items=items)
