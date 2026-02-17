# Parallelization Plan

## Goal

Improve throughput for the DeepSeek confidence experiment while keeping HPC resource requests tight and avoiding verifier instability (`Too many open files` / `.olean.private` open failures).

## Current Design (Implemented)

### 1) Two-stage pipeline per theorem

1. Generate `samples_per_theorem` proof attempts with bounded LLM concurrency:
   - `llm_parallel_requests` worker threads (network-bound).
2. Verify generated attempts with bounded Lean concurrency:
   - Group attempts into chunks of `lean_batch_size`.
   - Each chunk is verified by one Lean process via `LeanVerifier.verify_many(...)`.
   - Up to `lean_parallel_workers` chunk jobs run concurrently.

### 2) Batched Lean verification

- Old behavior: one Lean process per attempt.
  - For 512 attempts/theorem: 512 Lean processes.
- New behavior: one Lean process per chunk.
  - With `lean_batch_size=16`: 32 Lean processes/theorem.

Each batch file contains:
- one shared header/import block,
- N renamed theorem instances (`theorem_name_<sample_tag>`),
- one proof body per sample.

Lean diagnostics are parsed and mapped back to sample line ranges so each sample still gets an independent pass/fail verdict.

### 3) Resource envelope

Configured for the 512-scale DeepSeek run:
- `llm_parallel_requests = 4`
- `lean_parallel_workers = 4`
- `lean_batch_size = 16`

HPC request in `scripts/run_deepseek_scale_512.pbs`:
- `ncpus=8`, `mem=64gb`, `walltime=10:00:00`

Rationale:
- 4 verification workers + 4 LLM workers fit 8 CPU cores without aggressive oversubscription.
- Lean subprocesses are forced single-threaded (`LEAN_NUM_THREADS=1`; OMP/BLAS threads pinned to 1).
- Batch mode cuts process/file churn, which directly lowers FD pressure.

### 4) Lean subprocess cap (new)

A separate cap is now enforced for active Lean subprocesses, independent of theorem worker count:

- `lean_workers`: schedules theorem tasks.
- `lean_jobs`: passed to Lean as `-j` per subprocess.
- `lean_procs`: hard cap on concurrent `lake env lean` subprocesses (global within one run process).

Implementation:
- `src/proofconf/lean/verifier.py`:
  - adds a bounded semaphore guarding every `subprocess.run(...)` call,
  - reads defaults from env:
    - `PROOFCONF_LEAN_JOBS` (default `1`)
    - `PROOFCONF_LAKE_MAX_PROCS` (default `4`)
- `scripts/reverify_run.py`:
  - adds `--lean-jobs` and `--lean-procs`,
  - records both in JSON/markdown outputs.
- PBS scripts:
  - set `ulimit -n 65535`,
  - run preflight with explicit `lean -j`,
  - pass `--lean-jobs` and `--lean-procs`.

## Why This Fix Addresses the Prior Failure

The previous verifier mode spawned many short-lived Lean processes and repeatedly reopened compiled artifacts, which amplifies file descriptor and filesystem pressure under concurrency.

Batch mode reduces:
- number of Lean process launches,
- number of concurrent artifact-open cycles,
- per-attempt verifier overhead.

This is expected to improve throughput and reduce `fd_exhaustion` events.

The subprocess cap directly prevents ENFILE spikes (`Too many open files in system`) when theorem scheduling is high.

## Operational Notes

- Scratch storage is used for run/log/cache paths in PBS job:
  - `/scratch/$USER/data/proofconf/output/runs`
  - `/scratch/$USER/data/proofconf/output/logs`
  - `/scratch/$USER/data/proofconf/cache`
- Preflight Lean compile runs before experiment launch.
- Warmup failure aborts the run early.

## Validation Checklist Before Full Run

1. Submit one short canary with same parallel settings and fewer attempts/theorems.
2. Confirm:
   - no `fd_exhaustion` / file-open infra errors,
   - expected batch dispatch in `driver.log` (`verify_dispatch` events),
   - non-zero Lean pass count on sanity subset.
3. Launch full 512-scale run only after canary passes.

## Validation Results (2026-02-17)

1. Prior broken setting (`lean_workers=8`, no subprocess cap):
   - 10-theorem canary produced mostly `0/32` with ENFILE/open-file errors.
2. Fixed setting (`lean_workers=8`, `lean_jobs=1`, `lean_procs=4`):
   - same 10-theorem canary produced `32/32` for all 10,
   - no open-file errors.
3. Full reasoner rerun with fixed setting:
   - quantization collapse disappeared,
   - previously impossible flips (`old 32 -> new 0`) resolved.

## Follow-up Diagnosis and Fix (2026-02-17, 8-way target)

### Observed failure pattern

- With `lean_procs=8` on canary (`10` theorems x `32` attempts), failures were deterministic:
  - first `8` theorem tasks failed both batches (`16` failed batches total),
  - remaining tasks succeeded once concurrency dropped.
- Error signature remained:
  - `failed to open ... .olean: Too many open files in system`

This showed the bottleneck was import-time FD pressure at high simultaneous process start, not theorem content.

### Fix that made 8-way stable

`src/proofconf/lean/verifier.py` now:

1. Resolves `lake env` once at startup (`lake env printenv`) and then invokes direct `lean` for each verification call.
2. Keeps process launch staggering (`PROOFCONF_LAKE_LAUNCH_GAP_MS`, default `250ms`).
3. Prunes `import Aesop` when the proof text does not use `aesop` (configurable).
4. Deletes verifier temp files by default (configurable).

### New runtime knobs

- `PROOFCONF_DIRECT_LEAN` (default `1`)
  - `1`: run direct `lean` with cached env from `lake env printenv`
  - `0`: fallback to `lake env lean` per call
- `PROOFCONF_LAKE_LAUNCH_GAP_MS` (default `250`)
- `PROOFCONF_PRUNE_AESOP_IMPORT` (default `1`)
- `PROOFCONF_KEEP_TMP` (default `0`)

### Validation outcome

- Canary job `576547` (same 10-theorem debug set, `lean_workers=8`, `lean_procs=8`) passed:
  - `failed_batches=0`
  - return codes `{'0': 320}`
  - new distribution `32/32: 10`
- This is the first verified-stable 8-way configuration in this repo for reverify.

### Operational update

Reverify PBS scripts now export:

- `PROOFCONF_DIRECT_LEAN=1`
- `PROOFCONF_LAKE_LAUNCH_GAP_MS=250`
- `PROOFCONF_KEEP_TMP=0`

Three full model reverify jobs were submitted with `lean_procs=8` after this validation:

- `576548` (`deepseek-chat`)
- `576549` (`deepseek-reasoner`)
- `576550` (`gemini-2.5-flash`)
