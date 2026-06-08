"""POST /api/v1/verify — stream agent progress as SSE.

Drives the LangGraph compiled in app.agents.graph and translates per-node
state updates into the named SSE events documented in /api/openapi.yaml.

On the final verdict we persist a SearchRequest + Citations row so
GET /api/v1/history can show past runs.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Literal, overload

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import GraphNode, build_graph
from app.api.generated.models import (
    CandidatesFoundPayload,
    Error,
    FinalVerdictPayload,
    PassageFoundPayload,
    PassageVerdictPayload,
    SearchStartedPayload,
    SseEventType,
    VerifyRequest,
)
from app.domain.state import (
    FactCheckState,
    RetrievalOutput,
    SearchOutput,
    Verdict,
    VerificationOutput,
)
from app.platform.auth.dependencies import get_current_user
from app.platform.db.models import Citation, SearchRequest, User
from app.platform.db.session import session_scope

log = logging.getLogger(__name__)

# Single source of truth for which payload schema belongs to which SSE event.
# The @overload signatures enforce the same pairing at type-check time;
EVENT_PAYLOAD: dict[SseEventType, type[BaseModel] | None] = {
    SseEventType.search_started: SearchStartedPayload,
    SseEventType.candidates_found: CandidatesFoundPayload,
    SseEventType.passage_found: PassageFoundPayload,
    SseEventType.passage_verdict: PassageVerdictPayload,
    SseEventType.final_verdict: FinalVerdictPayload,
    SseEventType.error: Error,
    SseEventType.done: None,
}


@overload
def sse(
    event: Literal[SseEventType.search_started], data: SearchStartedPayload
) -> dict[str, str]: ...
@overload
def sse(
    event: Literal[SseEventType.candidates_found], data: CandidatesFoundPayload
) -> dict[str, str]: ...
@overload
def sse(
    event: Literal[SseEventType.passage_found], data: PassageFoundPayload
) -> dict[str, str]: ...
@overload
def sse(
    event: Literal[SseEventType.passage_verdict], data: PassageVerdictPayload
) -> dict[str, str]: ...
@overload
def sse(
    event: Literal[SseEventType.final_verdict], data: FinalVerdictPayload
) -> dict[str, str]: ...
@overload
def sse(event: Literal[SseEventType.error], data: Error) -> dict[str, str]: ...
@overload
def sse(event: Literal[SseEventType.done], data: None = ...) -> dict[str, str]: ...
def sse(event: SseEventType, data: BaseModel | None = None) -> dict[str, str]:
    expected = EVENT_PAYLOAD[event]
    if expected is None and data is not None:
        raise TypeError(f"{event.value!r} takes no payload, got {type(data).__name__}")
    if expected is not None and not isinstance(data, expected):
        got = type(data).__name__ if data is not None else "None"
        raise TypeError(f"{event.value!r} expects {expected.__name__}, got {got}")
    # mode="json" serialises enums to their value and AnyUrl to str
    return {
        "event": event.value,
        "data": json.dumps(data.model_dump(mode="json") if data else {}, ensure_ascii=False),
    }


async def _persist(state: FactCheckState, user_id: int) -> None:
    async with session_scope() as session:
        request = SearchRequest(
            user_id=user_id,
            claim=state.claim,
            verdict=state.final_verdict or Verdict.NOT_ENOUGH_INFO,
        )
        session.add(request)
        await session.flush()
        await session.refresh(request)
        for cite in state.citations or []:
            session.add(
                Citation(
                    request_id=request.id,
                    url=str(cite.url),
                    title=cite.title,
                    passage=cite.passage,
                    label=cite.label,
                    reasoning=cite.reasoning,
                )
            )
        await session.commit()


async def _event_stream(req: VerifyRequest, user_id: int) -> AsyncIterator[dict[str, str]]:
    graph = build_graph()
    initial = FactCheckState(
        claim=req.claim,
        prefer_source=req.prefer_source.value if req.prefer_source else "auto",
        retries=0,
    )

    verification: VerificationOutput | None = None
    try:
        async for update in graph.astream(initial, stream_mode="updates"):
            for node, delta in update.items():
                if delta is None:
                    continue
                if node == GraphNode.SEARCH:
                    search = SearchOutput.model_validate(delta)
                    yield sse(
                        SseEventType.search_started,
                        SearchStartedPayload(queries=search.search_queries),
                    )
                    # candidates are internal SearchHit; the wire shape is SearchCandidate
                    yield sse(
                        SseEventType.candidates_found,
                        CandidatesFoundPayload.model_validate(
                            {"items": [c.model_dump(mode="json") for c in search.candidates]}
                        ),
                    )
                elif node == GraphNode.RETRIEVE:
                    retrieval = RetrievalOutput.model_validate(delta)
                    for ev in retrieval.evidence:
                        yield sse(
                            SseEventType.passage_found,
                            PassageFoundPayload.model_validate(
                                {"url": ev.url, "title": ev.title, "passage": ev.text}
                            ),
                        )
                elif node == GraphNode.VERIFY:
                    verification = VerificationOutput.model_validate(delta)
                    for v in verification.passage_verdicts:
                        yield sse(
                            SseEventType.passage_verdict,
                            PassageVerdictPayload.model_validate(
                                {"url": v.url, "label": v.label, "reasoning": v.reasoning}
                            ),
                        )
                    yield sse(
                        SseEventType.final_verdict,
                        FinalVerdictPayload.model_validate(
                            {
                                "verdict": verification.final_verdict or Verdict.NOT_ENOUGH_INFO,
                                "citations": [
                                    c.model_dump(mode="json") for c in verification.citations
                                ],
                            }
                        ),
                    )
        if verification is not None:
            await _persist(initial.model_copy(update={
                "final_verdict": verification.final_verdict,
                "citations": verification.citations,
                "passage_verdicts": verification.passage_verdicts,
            }), user_id)
        else:
            raise RuntimeError("Verification did not complete")
        
        yield sse(SseEventType.done)

    except Exception as e:
        log.exception("Verify stream failed")
        yield sse(SseEventType.error, Error(code="internal", message=str(e)))


router = APIRouter(tags=["verify"])


@router.post("/api/v1/verify")
async def stream_verify(
    body: VerifyRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> EventSourceResponse:
    assert user.id is not None
    return EventSourceResponse(
        _event_stream(body, user.id),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )