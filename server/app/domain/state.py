"""
Distinct from the API-facing models in app/generated/models.py: this is the
internal pipeline state, not part of the public contract.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from app.tools.sources import Passage


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


class RetrievalOutput(BaseModel):
    evidence: list[Passage] = []


class VerificationOutput(BaseModel):
    passage_verdicts: list[PassageVerdict] = []
    final_verdict: Verdict | None = None
    citations: list[Citation] = []


class FactCheckState(RetrievalOutput, VerificationOutput):
    """One claim (or sub-claim) with the evidence gathered for it and its verdict."""

    claim: str
