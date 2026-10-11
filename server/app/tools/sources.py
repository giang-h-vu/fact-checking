"""Search source types — shared by tool implementations and agents."""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, Field

SearchSource = Literal["duckduckgo", "brave", "wikipedia"]


def is_transient(exc: BaseException) -> bool:
    """Worth another try: the network hiccuped or the server erred.

    A 4xx (403 paywall, 404, 429) answers the same again, so retrying only burns time and
    quota; the caller has its own fallback for those.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


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
