"""Per-request context, graph state and streamed events for the research agents.

Three kinds of data, kept apart on purpose:

* `Ctx` — immutable, per request, passed as the agent *context*. Holds what tools need
  but that must not travel through messages (settings, engines, the work dir).
* `ResearchState` / `ResearcherState` — graph *state*. Tools write it by returning a
  `Command`; the keys that parallel tool calls write to carry a reducer. Only
  `messages` ever reaches a model. Raw page text is never in state: pages live in
  files under `Ctx.workdir` and state holds `FileRef`s, so LangSmith (which records
  state) never sees an article.
* Events — what the SSE layer streams. Tools emit them through the stream writer.

No `from __future__ import annotations`: LangGraph reads reducers from the live
`Annotated[...]` hints.
"""

import asyncio
import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState
from pydantic import BaseModel, Field

from app.domain.state import PreferSource
from app.platform.config import Settings
from app.tools.sources import Passage, SearchHit, SearchSource

# --- events ------------------------------------------------------------------------


@dataclass
class PlanCreated:
    subclaims: list[str]


@dataclass
class SearchRan:
    query: str
    hits: list[SearchHit]


@dataclass
class PassageFound:
    todo_id: int
    passage: Passage


@dataclass
class CombinedEvidence:
    """The orchestrator marked a todo as needing facts from several sources together."""

    todo_id: int


@dataclass
class ResearchDone:
    subclaims: list[str]
    passages: list[list[Passage]]  # parallel to subclaims
    combined: list[bool]  # parallel to subclaims: judge the passages together


Event = PlanCreated | SearchRan | PassageFound | CombinedEvidence | ResearchDone


# --- context -----------------------------------------------------------------------


class SearchQuery(BaseModel):
    """One search the orchestrator asks for: what to look for, and where."""

    query: str = Field(description="The search query: key terms, not the whole claim.")
    engine: SearchSource = Field(
        description=(
            "wikipedia for encyclopedic facts; brave or duckduckgo for news, recent events "
            "and niche topics."
        )
    )


@dataclass(frozen=True)
class Ctx:
    settings: Settings
    engines: list[SearchSource]
    workdir: Path
    fetch_sem: asyncio.Semaphore


def available_engines(prefer_source: PreferSource, brave_api_key: str) -> list[SearchSource]:
    """Engines the researcher may use: `prefer_source` hint ∩ configured credentials."""
    if prefer_source == "wiki":
        return ["wikipedia"]
    web: list[SearchSource] = ["brave", "duckduckgo"] if brave_api_key else ["duckduckgo"]
    return web if prefer_source == "web" else ["wikipedia", *web]


# --- state -------------------------------------------------------------------------


class FileRef(TypedDict):
    """A fetched page saved to disk. `path` is under `Ctx.workdir`."""

    url: str
    title: str
    path: str


def merge_passages(
    old: dict[int, list[Passage]], new: dict[int, list[Passage]]
) -> dict[int, list[Passage]]:
    return {k: old.get(k, []) + new.get(k, []) for k in old.keys() | new.keys()}


def merge_pages(old: dict[int, list[str]], new: dict[int, list[str]]) -> dict[int, list[str]]:
    return {
        k: list(dict.fromkeys(old.get(k, []) + new.get(k, []))) for k in old.keys() | new.keys()
    }


def add_counts(old: dict[int, int], new: dict[int, int]) -> dict[int, int]:
    return {k: old.get(k, 0) + new.get(k, 0) for k in old.keys() | new.keys()}


class ResearchState(AgentState):
    """Orchestrator state. `todos` is added by `TodoListMiddleware`."""

    # Parallel `delegate` calls merge into these in the same step, hence the reducers.
    files: Annotated[NotRequired[dict[str, FileRef]], operator.or_]  # page_id -> file
    passages: Annotated[NotRequired[dict[int, list[Passage]]], merge_passages]  # by todo index
    pages: Annotated[NotRequired[dict[int, list[str]]], merge_pages]  # page_ids by todo index
    delegations: Annotated[NotRequired[dict[int, int]], add_counts]  # attempts by todo index


class ResearcherState(AgentState):
    """State of one researcher subagent: a single sub-claim."""

    subclaim: str
    todo_id: int  # index into the orchestrator's todos
    seen_urls: Annotated[list[str], operator.add]  # URLs a search returned (SSRF guard)
    files: Annotated[dict[str, FileRef], operator.or_]
    fetched: Annotated[list[str], operator.add]  # page_ids this attempt fetched or reused
    passages: Annotated[list[Passage], operator.add]  # this todo's, including earlier attempts


def backstop(limit: int) -> int:
    """`recursion_limit` for an agent whose real bound is a limit middleware.

    The middleware trips first; this only stops a model that ignores the block.
    """
    return 4 * limit + 5
