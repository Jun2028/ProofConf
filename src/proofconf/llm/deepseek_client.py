from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .types import LLMResponse, TokenLogProb


class DeepSeekClient:
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
        url = "https://api.deepseek.com/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "logprobs": True,
            "top_logprobs": top_logprobs,
        }
        # Keep non-reasoner models aligned with prior behavior while allowing
        # reasoner models to use their default thinking behavior.
        if "reasoner" not in self.model.lower():
            payload["thinking"] = {"type": "disabled"}

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                body = resp.text
                # Some DeepSeek models do not support logprobs; retry without
                # logprob fields so sampling/verifying can still proceed.
                if "logprob" in body.lower():
                    fallback_payload = {
                        "model": payload["model"],
                        "messages": payload["messages"],
                        "temperature": payload["temperature"],
                        "max_tokens": payload["max_tokens"],
                    }
                    if "thinking" in payload:
                        fallback_payload["thinking"] = payload["thinking"]
                    fallback = client.post(url, headers=headers, json=fallback_payload)
                    if fallback.status_code >= 400:
                        raise RuntimeError(
                            f"DeepSeek API fallback error {fallback.status_code}: {fallback.text[:800]}"
                        )
                    data = fallback.json()
                    data["_proofconf_logprobs_available"] = False
                else:
                    raise RuntimeError(f"DeepSeek API error {resp.status_code}: {resp.text[:800]}")
            else:
                data = resp.json()

        choice = data["choices"][0]
        text = choice.get("message", {}).get("content", "") or ""
        token_rows = choice.get("logprobs", {}).get("content", []) or []

        tokens: List[TokenLogProb] = []
        for row in token_rows:
            top = row.get("top_logprobs", []) or []
            top_pairs = [(item.get("token", ""), float(item.get("logprob", 0.0))) for item in top]
            tokens.append(
                TokenLogProb(
                    token=row.get("token", ""),
                    logprob=float(row.get("logprob", 0.0)),
                    top_logprobs=top_pairs,
                )
            )

        return LLMResponse(provider="deepseek", model=self.model, text=text, tokens=tokens, raw=data)
