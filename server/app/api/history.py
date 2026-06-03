"""GET /api/v1/history — recent verification requests with their citations."""
from __future__ import annotations

from typing import Annotated, Sequence, TypeVar
from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Select
from sqlmodel import col, select


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

T = TypeVar("T")

async def _fetch_all(session: AsyncSession, select_query: Select[tuple[T]]) -> Sequence[T]:
    return (await session.execute(select_query)).scalars().all()

router = APIRouter(tags=["history"])

@router.get("/api/v1/history", response_model=HistoryResponse)
async def list_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> HistoryResponse:
    async with session_scope() as session:
        requests  = await _fetch_all(
            session,
            select(SearchRequest).order_by(col(SearchRequest.created_at).desc()).limit(limit)
        )
        if not requests:
            return HistoryResponse(items=[])

        ids = [r.id for r in requests if r.id is not None]
        
        citations_by_request: dict[int, list[Citation]] = {rid: [] for rid in ids}
        citations = await _fetch_all(
            session,
            select(Citation).where(col(Citation.request_id).in_(ids))
        )
        for c in citations:
            citations_by_request[c.request_id].append(c)

    historyItems: list[HistoryItem] = []
    for r in requests:
        if r.id is not None:
            apiCitations: list[ApiCitation] = []
            for c in citations_by_request[r.id]:
                apiCitations.append(
                    ApiCitation.model_validate({
                        "url": c.url,
                        "title": c.title,
                        "passage": c.passage,
                        "label": c.label,
                        "reasoning": c.reasoning,
                    })  
                )

            historyItems.append(
                HistoryItem(
                    id=r.id,
                    claim=r.claim,
                    datetime=r.created_at,
                    verdict=Verdict(r.verdict),
                    citations=apiCitations,
                )
            )

    return HistoryResponse(items=historyItems)
