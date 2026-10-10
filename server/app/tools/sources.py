"""Search source types — shared by tool implementations and agents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SearchSource = Literal["duckduckgo", "brave", "wikipedia"]


class SearchHit(BaseModel):
    url: str
    title: str
    snippet: str
    source: SearchSource


class FetchedPage(BaseModel):
    """A whole fetched page. Never persisted or traced — only the extracted `Passage` is.

    `text` is excluded from repr: LangSmith records a tool's output as `str(output)`,
    so this keeps the raw article out of the `fetch_url` span.
    """

    url: str
    title: str
    text: str = Field(repr=False)


class Passage(BaseModel):
    """The sentences extracted from a page as evidence for the claim."""

    url: str
    title: str
    text: str
