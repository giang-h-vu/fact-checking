"""ClaimVerificationAgent — LLM judges entailment per passage, aggregates to a verdict.

Replaces the DeBERTa NLI model. For each passage, prompt the LLM for a
strict {SUPPORTED, REFUTED, NOT_ENOUGH_INFO} label plus a one-sentence
reason. A sub-claim's verdict = majority vote, with NOT_ENOUGH_INFO as the
tie-breaker (matches the original NLI vote logic). The overall verdict
combines the sub-claims: any REFUTED refutes, all SUPPORTED supports.

A sub-claim the orchestrator marked `combined` (a comparison, an order, a superlative:
no single passage can settle it) is judged in ONE call over all its passages together,
and every passage carries that label. Only marked sub-claims take that path.
"""

from __future__ import annotations

import logging
from asyncio import gather
from collections import Counter

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.domain.state import Citation, FactCheckState, PassageVerdict, Verdict, VerificationOutput
from app.platform.llm import UNUSABLE_ANSWER, get_llm
from app.tools.sources import Passage

log = logging.getLogger(__name__)

SYSTEM = """You are a fact-checking judge. Given a claim and a passage of evidence,
decide whether the passage SUPPORTS, REFUTES, or has NOT_ENOUGH_INFO about the claim.
Provide a one-sentence reasoning for your decision.
"""

JOINT_SYSTEM = """You are a fact-checking judge. Given a claim and several numbered passages
of evidence, decide whether the passages TAKEN TOGETHER support, refute, or have
NOT_ENOUGH_INFO about the claim. Combine facts stated in different passages (for example
two figures for a comparison), but use only what the passages state: if together they do
not settle the claim, answer NOT_ENOUGH_INFO. Provide a one-sentence reasoning.
"""

PASSAGE_PROMPT = """Claim: {claim}

Passage: {passage}
"""


class JudgeOutput(BaseModel):
    label: Verdict
    reasoning: str


async def _judge(
    claim: str, passage: str, config: RunnableConfig | None = None, system: str = SYSTEM
) -> tuple[Verdict, str]:
    prompt = PASSAGE_PROMPT.format(claim=claim, passage=passage)
    try:
        result = await (
            get_llm()
            .with_structured_output(JudgeOutput, method="json_schema")
            .ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)], config=config)
        )
        if not isinstance(result, JudgeOutput):
            raise TypeError(f"Unexpected structured output type: {type(result)}")
    except UNUSABLE_ANSWER:
        # A provider error (quota, outage, auth) is not a weak verdict: it propagates, so
        # it is reported as an error and never saved to history as NOT_ENOUGH_INFO.
        log.warning(
            "Judge structured output failed for passage; defaulting to NOT_ENOUGH_INFO",
            exc_info=True,
        )
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


async def claim_verification_agent(
    state: FactCheckState, config: RunnableConfig | None = None, combined: bool = False
) -> VerificationOutput:
    if combined and state.evidence:
        joined = "\n".join(f"[{i}] {ev.text}" for i, ev in enumerate(state.evidence, 1))
        joint = await _judge(state.claim, joined, config, JOINT_SYSTEM)
        judgements = [joint] * len(state.evidence)
    else:
        judgements = await gather(*(_judge(state.claim, ev.text, config) for ev in state.evidence))
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


def combine_verdicts(verdicts: list[Verdict]) -> Verdict:
    """Overall verdict from per-sub-claim verdicts (a compound claim needs every part)."""
    if Verdict.REFUTED in verdicts:
        return Verdict.REFUTED
    if verdicts and all(v == Verdict.SUPPORTED for v in verdicts):
        return Verdict.SUPPORTED
    return Verdict.NOT_ENOUGH_INFO


async def verify_subclaims(
    subclaims: list[str],
    passages: list[list[Passage]],
    config: RunnableConfig | None = None,
    combined: list[bool] | None = None,
) -> VerificationOutput:
    """Verify each sub-claim against its own passages and merge into one output."""
    marks = combined or [False] * len(subclaims)
    outputs = await gather(
        *(
            claim_verification_agent(FactCheckState(claim=claim, evidence=evidence), config, mark)
            for claim, evidence, mark in zip(subclaims, passages, marks, strict=True)
        )
    )
    return VerificationOutput(
        passage_verdicts=[v for o in outputs for v in o.passage_verdicts],
        final_verdict=combine_verdicts(
            [o.final_verdict or Verdict.NOT_ENOUGH_INFO for o in outputs]
        ),
        citations=[c for o in outputs for c in o.citations],
    )
