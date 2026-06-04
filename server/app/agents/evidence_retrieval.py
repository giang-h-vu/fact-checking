"""EvidenceRetrievalAgent — fetch candidate URLs and pull out claim-relevant passages.

Two stages:
  1. Concurrent fetch of every candidate URL (capped by MAX_CONCURRENT_FETCHES).
  2. For each non-empty page, ask the LLM to pick the 1-3 sentences most
     relevant to the claim. We send chunked text rather than the whole page
     to keep the prompt small.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from asyncio import Semaphore, gather
from pydantic import BaseModel

from app.domain.state import FactCheckState, RetrievalOutput
from app.platform.config import get_settings
from app.platform.llm import get_llm
from app.tools import fetch_url
from app.tools.sources import FetchedPage

log = logging.getLogger(__name__)

SYSTEM = """You are the evidence-extraction step of a fact-checking pipeline.

Given a claim and a truncated web article, return the 1 to 3 sentences from
the article that are MOST relevant to the claim — verbatim, joined by ' ... '
if multiple. If the article contains nothing relevant to the claim, set
passage to null.
"""

PASSAGE_PROMPT = """Claim: {claim}

Article (truncated):
{article}
"""


class PassageExtraction(BaseModel):
    passage: str | None


PAGE_CHAR_LIMIT = 10000  # keep prompt manageable for small local models


async def _fetch_one(url: str, sem: Semaphore) -> FetchedPage | None:
    async with sem:
        try:
            return await fetch_url.ainvoke({"url": url})
        except Exception as e:
            log.warning("Fetch failed for %s: %s", url, e)
            return None


async def _fetch_all(urls: list[str]) -> list[FetchedPage]:
    settings = get_settings()
    sem = Semaphore(settings.max_concurrent_fetches)
    coroutines = [_fetch_one(url, sem) for url in urls]
    results = await gather(*coroutines)
    return [r for r in results if r and r.text]


def _extract_passage(claim: str, page: FetchedPage) -> str | None:
    article = page.text[:PAGE_CHAR_LIMIT]
    prompt = PASSAGE_PROMPT.format(claim=claim, article=article)
    try:
        result = (
            get_llm()
            .with_structured_output(PassageExtraction)
            .invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
        )
        if not isinstance(result, PassageExtraction):
            raise TypeError(f"Unexpected structured output type: {type(result)}")
    except Exception:
        log.warning("Passage extraction structured output failed for %s", page.url)
        return None
    return result.passage or None


async def evidence_retrieval_agent(state: FactCheckState) -> RetrievalOutput:
    if not state.candidates:
        return RetrievalOutput()

    pages = await _fetch_all([c.url for c in state.candidates])
    log.info("Fetched %d/%d pages", len(pages), len(state.candidates))

    evidence: list[FetchedPage] = []
    for page in pages:
        passage = _extract_passage(state.claim, page)
        if passage:
            evidence.append(FetchedPage(url=page.url, title=page.title, text=passage))
    log.info("Kept %d passages with evidence", len(evidence))
    return RetrievalOutput(evidence=evidence)
