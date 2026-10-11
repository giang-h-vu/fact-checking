"""Structured reflection for the orchestrator. Does no work; the call itself is the point."""

from langchain_core.tools import tool


@tool(parse_docstring=True)
def think_tool(findings: str, gaps: str, next_step: str) -> str:
    """Reflect on the research summaries and decide the next step. Call it alone, never in
    the same turn as another tool.

    Go through every todo:
    - Evidence: how many passages it has, and from which sources.
    - Fit: do the passages address the todo itself, or only its topic? For a comparison,
      is there a passage for each side?
    - Gaps: what is missing, one-sided, or contradicted between sources?
    - Options: what has NOT been tried for it yet (other terms, another engine, a focus
      on the saved pages), and how many retries it has left?

    Keep each field to a few short lines.

    Args:
        findings: Per todo, the passages it has and what they cover.
        gaps: Per todo, what is missing, one-sided or contradictory, and what was not yet tried.
        next_step: The exact delegate call(s) to make next, or "finish" when every todo has passages that address it or nothing untried remains.
    """
    # The arguments are already in the model's context as the call; echoing them would
    # only bill them again on every later turn.
    return "Reflection recorded."
