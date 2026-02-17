# Log-Probability Behavior (Observed)

Date: 2026-02-13 (UTC)

## Scope

Observed API behavior for token logprobs during setup and initial runs:
- DeepSeek Chat (`deepseek-chat`)
- Gemini Flash 2.5 (`gemini-2.5-flash`)

The pipeline requests top-20 alternatives where supported.

## DeepSeek Chat

Request mode:
- `logprobs: true`
- `top_logprobs: 20`
- thinking disabled (`{"type":"disabled"}`)

Observed response behavior:
- Returns per-token chosen logprob entries.
- Returns per-step top-token alternatives (`top_logprobs`) up to requested bound.
- Compatible with token-window confidence computation.

Pipeline handling:
- Uses chosen-token logprob sequence.
- Computes LGC and Bottom-10% over sliding token windows.

## Gemini 2.5 Flash

Request mode attempted:
- `generationConfig.responseLogprobs = true`
- `generationConfig.logprobs = 20`

Observed response behavior:
- Returns HTTP 400 INVALID_ARGUMENT with message:
  - `Logprobs is not enabled for models/gemini-2.5-flash`

Fallback behavior implemented:
- Retry without logprob fields.
- Generation succeeds, but token logprobs are unavailable.

Pipeline handling:
- Records sample/verdict normally.
- Token confidence metrics recorded as `NaN` for Gemini samples.

## Implication for Comparison

- DeepSeek supports confidence metrics in this setup.
- Gemini 2.5 Flash (current account/model access) does not expose token logprobs, so confidence-based comparison is limited to DeepSeek while correctness/pass-rate comparison can still include both.
