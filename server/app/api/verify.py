"""POST /api/v1/verify — stream agent progress as SSE.

Runs the research agents (app.agents.orchestrator), then verifies each sub-claim's
passages, translating both into the named SSE events documented in /api/openapi.yaml.

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

from app.agents.claim_verification import verify_subclaims
from app.agents.orchestrator import research
from app.agents.run import PassageFound, PlanCreated, ResearchDone, SearchRan
from app.api.generated.models import (
    CandidatesFoundPayload,
    Error,
    FinalVerdictPayload,
    PassageFoundPayload,
    PassageVerdictPayload,
    PlanCreatedPayload,
    SearchStartedPayload,
    SseEventType,
    VerifyRequest,
)
from app.domain.state import FactCheckState, PreferSource, Verdict
from app.platform.auth.dependencies import get_current_user
from app.platform.db.models import Citation, SearchRequest, User
from app.platform.db.session import session_scope
from app.platform.tracing import fact_check_run, trace_config

log = logging.getLogger(__name__)

# Single source of truth for which payload schema belongs to which SSE event.
# The @overload signatures enforce the same pairing at type-check time;
EVENT_PAYLOAD: dict[SseEventType, type[BaseModel] | None] = {
    SseEventType.plan_created: PlanCreatedPayload,
    SseEventType.search_started: SearchStartedPayload,
    SseEventType.candidates_found: CandidatesFoundPayload,
    SseEventType.passage_found: PassageFoundPayload,
    SseEventType.passage_verdict: PassageVerdictPayload,
    SseEventType.final_verdict: FinalVerdictPayload,
    SseEventType.error: Error,
    SseEventType.done: None,
}


@overload
def sse(event: Literal[SseEventType.plan_created], data: PlanCreatedPayload) -> dict[str, str]: ...
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
    prefer: PreferSource = req.prefer_source.value if req.prefer_source else "auto"
    done: ResearchDone | None = None
    try:
        async with fact_check_run(req.claim, trace_config(user_id, prefer)) as run_config:
            async for event in research(req.claim, prefer, run_config):
                if isinstance(event, PlanCreated):
                    yield sse(
                        SseEventType.plan_created, PlanCreatedPayload(subclaims=event.subclaims)
                    )
                elif isinstance(event, SearchRan):
                    yield sse(
                        SseEventType.search_started, SearchStartedPayload(queries=[event.query])
                    )
                    # hits are internal SearchHit; the wire shape is SearchCandidate
                    yield sse(
                        SseEventType.candidates_found,
                        CandidatesFoundPayload.model_validate(
                            {"items": [h.model_dump(mode="json") for h in event.hits]}
                        ),
                    )
                elif isinstance(event, PassageFound):
                    p = event.passage
                    yield sse(
                        SseEventType.passage_found,
                        PassageFoundPayload.model_validate(
                            {"url": p.url, "title": p.title, "passage": p.text}
                        ),
                    )
                elif isinstance(event, ResearchDone):
                    done = event
            if done is None:
                raise RuntimeError("Research did not complete")

            verification = await verify_subclaims(
                done.subclaims, done.passages, run_config, done.combined
            )
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
                    "citations": [c.model_dump(mode="json") for c in verification.citations],
                }
            ),
        )
        await _persist(
            FactCheckState(
                claim=req.claim,
                final_verdict=verification.final_verdict,
                citations=verification.citations,
                passage_verdicts=verification.passage_verdicts,
            ),
            user_id,
        )
        yield sse(SseEventType.done)

    except Exception:
        # The detail (provider errors can carry URLs, model names, account state) goes to
        # the log only; the client gets a fixed message.
        log.exception("Verify stream failed")
        yield sse(
            SseEventType.error,
            Error(code="internal", message="The fact-check could not be completed. Try again."),
        )


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
