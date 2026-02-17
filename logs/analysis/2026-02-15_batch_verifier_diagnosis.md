# Diagnosis: Quantized Pass Rates (`0`, `0.5`, `1.0`) Were Pipeline-Induced

## Context

User reported that per-theorem pass rates were implausibly quantized to:
- `0/32`
- `16/32`
- `32/32`

This document records the investigation and root cause.

## What Was Checked

### 1) Storage/Join Integrity (`samples` vs `verdicts`)

For both runs:
- `2026-02-15_043621Z_gemini25flash_prescreen_l1_l3_32`
- `2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32`

Checks showed:
- no duplicate `sample_id` rows in `samples.jsonl`
- no duplicate `sample_id` rows in `verdicts.jsonl`
- no orphan verdict rows (`verdict_without_sample = 0`)

So this is not a simple write/read corruption issue.

### 2) Batch-Level Pattern Check

Using `source_path` batch suffix (`..._b0.lean` / `..._b1.lean`), per-batch outcomes were computed.

Gemini run:
- batch distribution: `0/16` for `355` batches, `16/16` for `35` batches
- for all `195` theorems, each theorem’s two batches were exactly binary (`0/16` or `16/16`)

DeepSeek reasoner partial run:
- batch distribution: `0/16` for `98` batches, `16/16` for `60` batches
- for all `79` touched theorems, same binary batch behavior

This mechanically explains theorem-level quantization:
- both batches fail -> `0/32`
- one pass, one fail -> `16/32` (=`0.5`)
- both pass -> `32/32`

### 3) Same-Proof Contradiction Check

Exact same raw completion text (no whitespace collapsing) was sometimes both pass and fail for the same theorem, e.g.:
- `ring`
- `native_decide`
- `rw [h₀, h₁]\nnorm_num`

This indicates evaluator attribution problems rather than genuine model variability.

### 4) Verifier Internal Reproduction

A failing verdict row (`mathd_algebra_55`, DeepSeek reasoner) was replayed through:
- `LeanVerifier._extract_diagnostics(...)`

Before fix:
- `block_count = 0` despite Lean error text being present.

Why:
- diagnostic path in Lean output was `/nfs/...`
- verifier compared against `source_path.resolve()`, which became `/scratch/...` (symlink-resolved path)
- path mismatch caused diagnostics to be discarded.

When diagnostics were discarded, `verify_many` fell back to “no parsed diagnostics” behavior and marked the whole 16-sample batch failed.

## Root Cause

In `src/proofconf/lean/verifier.py`, `_extract_diagnostics` compared:
- unresolved diagnostic absolute path (`/nfs/...`)
against
- resolved source path (`/scratch/...`)

Because both refer to the same file via symlinked mounts, this mismatch should have been normalized but was not.

## Fix Applied

File:
- `src/proofconf/lean/verifier.py`

Change:
- normalize diagnostic path with `resolve()` for both absolute and relative paths before comparison to target.

Validation after fix on the same failing example:
- diagnostics are now extracted (`block_count = 8`, first error line parsed correctly).

## Impact on Existing Results

Any run relying on batched verification (`lean_batch_size=16`) in this environment may be biased toward theorem rates in `{0, 0.5, 1.0}` due to batch-level misattribution.

Therefore, previously reported correlation/selection conclusions from these affected runs should be treated as invalid until rerun with the fix.

## Recommended Next Steps

1. Rerun the prescreens with the patched verifier.
2. Keep `lean_batch_size=16` initially (faster), then spot-check a subset with `lean_batch_size=1` to confirm no residual attribution artifacts.
3. Recompute theorem inclusion and confidence analysis from the rerun outputs.

