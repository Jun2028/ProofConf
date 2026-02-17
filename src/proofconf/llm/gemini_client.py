from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .types import LLMResponse, TokenLogProb


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout_s: int = 120):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        top_logprobs: int,
    ) -> LLMResponse:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseLogprobs": True,
                "logprobs": min(20, max(0, int(top_logprobs))),
            },
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(
                url,
                json=payload,
                headers={"x-goog-api-key": self.api_key},
            )
            if resp.status_code >= 400:
                body = resp.text
                if "Logprobs is not enabled" in body:
                    fallback_payload = {
                        "systemInstruction": payload["systemInstruction"],
                        "contents": payload["contents"],
                        "generationConfig": {
                            "temperature": temperature,
                            "maxOutputTokens": max_tokens,
                        },
                    }
                    fallback = client.post(
                        url,
                        json=fallback_payload,
                        headers={"x-goog-api-key": self.api_key},
                    )
                    if fallback.status_code >= 400:
                        raise RuntimeError(
                            f"Gemini API fallback error {fallback.status_code}: {fallback.text[:800]}"
                        )
                    data = fallback.json()
                    candidate = (data.get("candidates") or [{}])[0]
                    parts = ((candidate.get("content") or {}).get("parts") or [])
                    text = "\n".join(part.get("text", "") for part in parts if "text" in part).strip()
                    data["_proofconf_logprobs_available"] = False
                    return LLMResponse(
                        provider="gemini",
                        model=self.model,
                        text=text,
                        tokens=[],
                        raw=data,
                    )

                raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:800]}")
            data = resp.json()

        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "\n".join(part.get("text", "") for part in parts if "text" in part).strip()

        tokens: List[TokenLogProb] = []
        logprobs_result: Dict[str, Any] = candidate.get("logprobsResult") or {}
        chosen_candidates = logprobs_result.get("chosenCandidates") or []
        top_candidates = logprobs_result.get("topCandidates") or []

        for idx, chosen in enumerate(chosen_candidates):
            top_entries = []
            if idx < len(top_candidates):
                for item in top_candidates[idx].get("candidates", []) or []:
                    top_entries.append((item.get("token", ""), float(item.get("logProbability", 0.0))))

            tokens.append(
                TokenLogProb(
                    token=chosen.get("token", ""),
                    logprob=float(chosen.get("logProbability", 0.0)),
                    top_logprobs=top_entries,
                )
            )

        return LLMResponse(provider="gemini", model=self.model, text=text, tokens=tokens, raw=data)
