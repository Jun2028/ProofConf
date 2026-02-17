# 2026-02-17 Parallel-8 Verifier Diagnosis and Fix

## Problem

Reverify runs at `lean_procs=8` were unstable with:

- `failed to open ... .olean: Too many open files in system`
- deterministic canary collapse (`16/20` failed batches on 10-theorem canary)

`lean_procs=4` was stable but did not meet the target parallel level.

## Diagnostic observations

1. Failure shape was concurrency-linked:
   - first 8 theorem tasks failed, later tasks succeeded as active concurrency dropped.
2. Increasing timeout did not help.
3. Launch-gap and Aesop-pruning alone did not fix `lean_procs=8`.
4. Error was infrastructure-level file-open pressure, not theorem correctness.

## Implemented fix

In `src/proofconf/lean/verifier.py`:

1. Resolve `lake env` once (`lake env printenv`) and invoke direct `lean` per check.
2. Keep launch staggering (`PROOFCONF_LAKE_LAUNCH_GAP_MS`, default `250`).
3. Prune `import Aesop` when proof text does not contain `aesop` (default on).
4. Clean up verifier temp files by default (default keep off).

In reverify PBS scripts:

- export `PROOFCONF_DIRECT_LEAN=1`
- export `PROOFCONF_LAKE_LAUNCH_GAP_MS=250`
- export `PROOFCONF_KEEP_TMP=0`

## Validation

Canary rerun (same 10 theorem debug set) after fix:

- Job: `576547`
- Settings: `lean_workers=8`, `lean_jobs=1`, `lean_procs=8`
- Result:
  - `failed_batches=0`
  - return codes `{'0': 320}`
  - distribution `32/32: 10`

This confirms stable 8-way reverify in this repo with the new verifier path.

## Follow-up jobs submitted

After canary pass, full three-model reverify jobs were submitted with `lean_procs=8`:

- `576548` (`deepseek-chat`)
- `576549` (`deepseek-reasoner`)
- `576550` (`gemini-2.5-flash`)
