"""Search source types — shared by tool implementations and agents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SearchSource = Literal["duckduckgo", "brave", "wikipedia"]


class SearchHit(BaseModel):
    url: str
    title: str
    snippet: str
    source: SearchSource


class FetchedPage(BaseModel):
    url: str
    title: str
    text: str
