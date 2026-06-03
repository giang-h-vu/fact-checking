"""
Distinct from the API-facing models in app/generated/models.py: this is the
internal pipeline state, not part of the public contract. Keep it append-only
where possible so each agent step sees what previous agent step produced.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from app.tools.sources import FetchedPage, SearchHit


class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    NOT_ENOUGH_INFO = "NOT_ENOUGH_INFO"


PreferSource = Literal["auto", "wiki", "web"]


class PassageVerdict(BaseModel):
    url: str
    title: str
    passage: str
    label: Verdict
    reasoning: str


class Citation(BaseModel):
    url: str
    title: str
    passage: str
    label: Verdict
    reasoning: str = ""

class SearchOutput(BaseModel):
    search_queries: list[str] = []
    candidates: list[SearchHit] = []


class RetrievalOutput(BaseModel):
    evidence: list[FetchedPage] = []


class VerificationOutput(BaseModel):
    passage_verdicts: list[PassageVerdict] = []
    final_verdict: Verdict | None = None
    citations: list[Citation] = []

class FactCheckState(SearchOutput, RetrievalOutput, VerificationOutput):
    # Input
    claim: str
    prefer_source: PreferSource = "auto"

    # Loop control
    retries: int = 0
    error: str | None = None