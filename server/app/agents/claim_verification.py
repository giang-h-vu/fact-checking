"""ClaimVerificationAgent — LLM judges entailment per passage, aggregates to a verdict.

Replaces the DeBERTa NLI model. For each passage, prompt the LLM for a
strict {SUPPORTED, REFUTED, NOT_ENOUGH_INFO} label plus a one-sentence
reason. Final verdict = majority vote, with NOT_ENOUGH_INFO as the
tie-breaker (matches the original NLI vote logic).
"""

from __future__ import annotations

import logging
from asyncio import gather
from collections import Counter

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.domain.state import Citation, FactCheckState, PassageVerdict, Verdict, VerificationOutput
from app.platform.llm import get_llm

log = logging.getLogger(__name__)

SYSTEM = """You are a fact-checking judge. Given a claim and a passage of evidence,
decide whether the passage SUPPORTS, REFUTES, or has NOT_ENOUGH_INFO about the claim.
Provide a one-sentence reasoning for your decision.
"""

PASSAGE_PROMPT = """Claim: {claim}

Passage: {passage}
"""


class JudgeOutput(BaseModel):
    label: Verdict
    reasoning: str


async def _judge(claim: str, passage: str) -> tuple[Verdict, str]:
    prompt = PASSAGE_PROMPT.format(claim=claim, passage=passage)
    try:
        result = await (
            get_llm()
            .with_structured_output(JudgeOutput, method="json_schema")
            .ainvoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
        )
        if not isinstance(result, JudgeOutput):
            raise TypeError(f"Unexpected structured output type: {type(result)}")
    except Exception:
        log.warning("Judge structured output failed for passage; defaulting to NOT_ENOUGH_INFO")
        return Verdict.NOT_ENOUGH_INFO, "Judge response malformed"

    return result.label, result.reasoning


def _aggregate(verdicts: list[PassageVerdict]) -> Verdict:
    if not verdicts:
        return Verdict.NOT_ENOUGH_INFO
    counts = Counter(v.label for v in verdicts)
    supported = counts.get(Verdict.SUPPORTED, 0)
    refuted = counts.get(Verdict.REFUTED, 0)
    if supported == refuted:
        return Verdict.NOT_ENOUGH_INFO
    if supported > refuted:
        return Verdict.SUPPORTED
    return Verdict.REFUTED


async def claim_verification_agent(state: FactCheckState) -> VerificationOutput:
    judgements = await gather(*(_judge(state.claim, ev.text) for ev in state.evidence))
    passage_verdicts: list[PassageVerdict] = []
    for ev, (label, reasoning) in zip(state.evidence, judgements, strict=False):
        passage_verdicts.append(
            PassageVerdict(
                url=ev.url, title=ev.title, passage=ev.text, label=label, reasoning=reasoning
            )
        )

    final = _aggregate(passage_verdicts)
    citations: list[Citation] = []
    for v in passage_verdicts:
        if v.label != Verdict.NOT_ENOUGH_INFO or final == Verdict.NOT_ENOUGH_INFO:
            citations.append(
                Citation(
                    url=v.url,
                    title=v.title,
                    passage=v.passage,
                    label=v.label,
                    reasoning=v.reasoning,
                )
            )
    log.info("Final verdict: %s (from %d passages)", final, len(passage_verdicts))
    return VerificationOutput(
        passage_verdicts=passage_verdicts, final_verdict=final, citations=citations
    )