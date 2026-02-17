from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class TokenLogProb:
    token: str
    logprob: float
    top_logprobs: List[Tuple[str, float]]


@dataclass
class LLMResponse:
    provider: str
    model: str
    text: str
    tokens: List[TokenLogProb]
    raw: Dict[str, Any]
