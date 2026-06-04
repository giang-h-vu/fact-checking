from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from langgraph.graph import END, StateGraph
from app.agents.claim_verification import claim_verification_agent
from app.agents.document_search import document_search_agent
from app.agents.evidence_retrieval import evidence_retrieval_agent
from app.domain.state import FactCheckState

MAX_RETRIES = 2

"""LangGraph StateGraph wiring.

```
       ┌─ search ◀──┐
       ▼            │ retry (≤2) if no evidence
   retrieve ────────┘
       │
       ▼
     verify
       │
       ▼
      END
```

`build_graph()` is cached because compiling a graph is non-trivial — every
HTTP request re-uses the same compiled instance.
"""


class GraphNode(str, Enum):
    SEARCH = "search"
    RETRIEVE = "retrieve"
    VERIFY = "verify"
    RETRY = "bump_retries"


def _route_after_retrieval(state: FactCheckState) -> Literal[GraphNode.SEARCH, GraphNode.VERIFY]:
    if not state.evidence and state.retries < MAX_RETRIES:
        return GraphNode.SEARCH
    return GraphNode.VERIFY


# .model_copy to use Pydantic validation at runtime
def _bump_retries(state: FactCheckState) -> FactCheckState:
    return state.model_copy(update={"retries": state.retries + 1})


@lru_cache
def build_graph():
    g = StateGraph(FactCheckState)
    g.add_node(GraphNode.SEARCH, document_search_agent)
    g.add_node(GraphNode.RETRIEVE, evidence_retrieval_agent)
    g.add_node(GraphNode.VERIFY, claim_verification_agent)
    g.add_node(GraphNode.RETRY, _bump_retries)

    g.set_entry_point(GraphNode.SEARCH)
    g.add_edge(GraphNode.SEARCH, GraphNode.RETRIEVE)
    g.add_conditional_edges(
        GraphNode.RETRIEVE,
        _route_after_retrieval,
        {GraphNode.SEARCH: GraphNode.RETRY, GraphNode.VERIFY: GraphNode.VERIFY},
    )
    g.add_edge(GraphNode.RETRY, GraphNode.SEARCH)
    g.add_edge(GraphNode.VERIFY, END)
    return g.compile()
