# ProofConf

A reproducible pipeline to study whether token-confidence signals from LLM-generated Lean proofs correlate with proof correctness.

## Goal

For each generated proof attempt:
1. Generate a full Lean proof body from an LLM.
2. Capture token-level log-probabilities when available.
3. Verify the proof with Lean.
4. Compute confidence metrics (Lowest Group Confidence, Bottom-10% Group Confidence).
5. Compare confidence against Lean pass/fail outcomes.

## Confidence Computation

This repo currently uses token logprob-based scores (higher is more confident):

- `token_score[i] = logprob(chosen_token_i)`
- Sliding windows on token scores with `window_size=24`, `stride=6`
- `LGC = min(window_mean_j)`
- `Bottom10 = mean(lowest 10% of window_mean_j)`

For interpretability, the pipeline also annotates the weakest token window with
line-range context and optional tactic-like span indices when segmentation is reliable.

If token logprobs are unavailable for a provider/model, confidence metrics are recorded as `NaN` and pass/fail comparison is still logged.

## Repository Layout

- `src/proofconf/` core pipeline (dataset loading, API clients, verifier, metrics, logging)
- `scripts/setup_minif2f.sh` Lean dependency setup (cache-aware, scratch-backed)
- `scripts/test.sh` setup smoke test with structured logs
- `scripts/run.sh` initial experiment run
- `configs/initial_run.json` initial experiment config
- `runs/<run_id>/` scientific artifacts (`samples.jsonl`, `verdicts.jsonl`, `metrics.jsonl`, `summary.*`)
- `logs/run/<run_id>/` driver logs and env/git snapshots
- `set-up-logs/` setup-test records

## Prerequisites

- `uv`
- `elan`/`lake`/`lean` toolchain
- API keys in:
  - `.secrets/deepseek.env` (`export DEEPSEEK_API_KEY=...`)
  - `.secrets/gemini.env` (`export GEMINI_API_KEY=...`)

## Setup

```bash
uv venv
uv sync
scripts/setup_minif2f.sh
scripts/test.sh
```

Notes:
- miniF2F heavy artifacts are set up to use `/scratch/$USER/data/proofconf`.
- `scripts/setup_minif2f.sh` uses `lake exe cache get` with TLS settings for this environment.

## Run Initial Experiment

```bash
scripts/run.sh
```

Default config (`configs/initial_run.json`):
- dataset: `docs/miniF2F-Graded.json`
- split: `valid`
- difficulty levels: `Level 2`, `Level 3`
- theorems: `3`
- samples per theorem per model: `2`
- models: `deepseek-chat`, `gemini-2.5-flash`

## First Run Results

Reference run: `runs/2026-02-13_185247Z_initial`

- DeepSeek (`deepseek-chat`)
  - attempts: `6`
  - Lean pass count: `2`
  - Lean pass rate: `0.333`
  - mean LGC: `-0.0095`
  - pass mean LGC: `-0.0248`
  - fail mean LGC: `-0.0018`

- Gemini (`gemini-2.5-flash`)
  - attempts: `6`
  - Lean pass count: `0`
  - Lean pass rate: `0.000`
  - token logprobs unavailable via this API setup, so confidence metrics are `NaN`

## Current Known Limitation

In this environment/API access, Gemini 2.5 Flash rejects token logprob requests (`Logprobs is not enabled for models/gemini-2.5-flash`). The pipeline falls back to generation without logprobs and records `NaN` confidence metrics for those samples.
