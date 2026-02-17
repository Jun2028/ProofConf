# Corrected Diagnosis for Three Most Recent Model Runs

> [STATUS UPDATE on 2026-02-15]
> The section "Replay of representative `32/32` theorem per model" is currently provisional.
> A later full re-evaluation run for DeepSeek Reasoner produced internally inconsistent results
> (e.g., many `old_pass=32` theorems reported as `new_pass=0`, while direct reproduction on the same theorem succeeds),
> so those replay bullets should not be treated as final until the re-evaluator run pipeline is corrected and rerun.

> [STATUS UPDATE on 2026-02-16]
> Root cause identified for invalid reverify artifacts: the PBS reverify scripts used `cp -al` to create per-job
> miniF2F trees, which hardlinked files across jobs instead of isolating them. This allowed cross-job interference
> on shared miniF2F artifacts (`.lake`/`.proofconf_tmp`) and produced unreliable full-run outputs.
> The old JSON outputs at:
> - `/scratch/USER/data/proofconf/reverify/2026-02-14_174421Z_deepseek_prescreen_l1_l3_32.reverify.json`
> - `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32.reverify.json`
> - `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_gemini25flash_prescreen_l1_l3_32.reverify.json`
> should be treated as invalid/stale for diagnosis.
> 
> Isolation fix: removed `cp -al`; jobs now use shared base miniF2F root with per-job isolated
> `PROOFCONF_TMP_ROOT` and `XDG_CACHE_HOME`. Clean reruns were submitted as:
> `575897` (DeepSeek chat), `575898` (DeepSeek reasoner), `575899` (Gemini 2.5 Flash).
> 
> Canary confirmation (`2026-02-16T02:01:47Z`): theorem
> `algebra_2rootsintpoly_am10tap11eqasqpam110` reverified as `old_pass=32, new_pass=32`, confirming the
> earlier `32 -> 0` flip was artifact-level corruption, not theorem-level behavior.

> [STATUS UPDATE on 2026-02-17]
> Root cause of the near-all-zero reverify outputs has now been concretely identified from instrumented PBS reruns:
> Lean repeatedly fails with:
> - `error: failed to open '.../*.olean': Too many open files in system`
> - `error: failed to open file '.../*.olean'`
> where the referenced `.olean` paths do exist on disk.
>
> Evidence artifacts:
> - `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32.debug_iso_cache.json`
> - `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32.debug_default_cache.json`
> - PBS logs `logs/pbs/576451.stdct-mgmt-02.OU`, `logs/pbs/576452.stdct-mgmt-02.OU`, `logs/pbs/576463.stdct-mgmt-02.OU`
>
> Key debug summary (`debug_iso_cache`, before retry patch):
> - `failed_batches=160/160`
> - `returncode_totals={'1': 2548}`
> - first-batch stderr lines explicitly report ENFILE (`Too many open files in system`) while opening Mathlib oleans.
>
> Post-patch verifier retry runs (retrying transient open-file failures) still show ENFILE-driven failure spikes under
> `lean_workers=8` on compute nodes, which indicates infrastructure/file-descriptor pressure remains the dominant source
> of misclassification in these full parallel reverify runs.
>
> Control confirmation (`2026-02-16T17:00:41Z`, serial worker run):
> - Artifact: `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32.debug_serial10.json`
> - Settings: `lean_workers=1`, 10 theorems that were previously `old=32,new=0` under broken parallel reruns.
> - Result: all 10 became `new=32/32`, with `failed_batches=0`, `returncode_totals={'0': 320}`,
>   and no `failed to open` / `Too many open files in system` errors.
>
> This isolates the failure to high-concurrency Lean verification pressure on shared infrastructure
> (file-descriptor exhaustion), not theorem content or a deterministic evaluator logic bug.

> [STATUS UPDATE on 2026-02-17 (Parallelization Fix Verified)]
> The reverify pipeline was updated to align with the robust pattern used in `/home/USER/openevolve`:
> - explicit Lean job pinning (`lean -j 1`),
> - raised file-descriptor limit in PBS (`ulimit -n 65535`),
> - and (critical) a separate cap on concurrent Lean subprocesses (`lean_procs`) independent of theorem worker threads.
>
> New verifier controls:
> - `lean_workers`: theorem-level worker threads (scheduler parallelism),
> - `lean_jobs`: Lean internal job count per subprocess (`-j`),
> - `lean_procs`: maximum concurrent `lake env lean` subprocesses across all workers.
>
> Validation:
> 1. Canary with problematic 10-theorem set, `lean_workers=8`, `lean_jobs=1`, `lean_procs=4`:
>    - Artifact: `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32.debug_parallel10.json`
>    - Result: `32/32` on all 10 theorems, zero failed batches, zero open-file errors.
> 2. Full reasoner rerun with same controls:
>    - Artifact: `/scratch/USER/data/proofconf/reverify/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32.reverify.json`
>    - Result: non-quantized distribution restored; `old32_new0 = 0`, `old32_new32 = 28`, `non_quantized = 33`.
>
> Conclusion: the original quantized/zeroed artifacts were caused by unbounded Lean subprocess pressure.
> The corrected parallelization strategy fixes this without disabling theorem-level parallel workers.

## Scope

This diagnosis covers one recent run per model:

- DeepSeek chat: `2026-02-14_174421Z_deepseek_prescreen_l1_l3_32`
- DeepSeek reasoner: `2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32`
- Gemini 2.5 Flash: `2026-02-15_043621Z_gemini25flash_prescreen_l1_l3_32`

Run roots:

- `/scratch/USER/data/proofconf/output/runs/2026-02-14_174421Z_deepseek_prescreen_l1_l3_32`
- `/scratch/USER/data/proofconf/output/runs/2026-02-15_043621Z_deepseek_reasoner_prescreen_l1_l3_32`
- `/scratch/USER/data/proofconf/output/runs/2026-02-15_043621Z_gemini25flash_prescreen_l1_l3_32`

## What Was Checked

1. `samples.jsonl` vs `verdicts.jsonl` integrity (missing/orphan IDs).
2. Theorem pass-count distribution (e.g., `0/32`, `16/32`, `32/32`).
3. Batch-level distribution by `source_path` suffix `_b0.lean`, `_b1.lean`.
4. Contradictions where identical `(theorem, text)` appears as both pass and fail.
5. Targeted replay checks with the patched verifier on representative `16/32` and `32/32` theorems.

## Raw Run-Level Findings

### 1) DeepSeek Chat (`2026-02-14_174421Z...`)

- Samples: `6239`
- Verdicts: `6239`
- Missing verdicts: `0`
- Theorem rate distribution:
  - `0/31`: `1`
  - `0/32`: `182`
  - `16/32`: `1`
  - `32/32`: `11`
- Batch distribution:
  - `0/15`: `1`
  - `0/16`: `366`
  - `16/16`: `23`
- Binary-batch theorems: `195/195`
- Same-text pass/fail contradictions: `1`
  - Example: `mathd_numbertheory_102`, text `norm_num`, fail `14`, pass `16`

### 2) DeepSeek Reasoner (`2026-02-15_043621Z...`)

- Samples: `2548`
- Verdicts: `2528`
- Missing verdicts: `20` (partial run)
- Theorem rate distribution:
  - `0/32`: `47`
  - `16/32`: `4`
  - `32/32`: `28`
- Batch distribution:
  - `0/16`: `98`
  - `16/16`: `60`
- Binary-batch theorems: `79/79`
- Same-text pass/fail contradictions: `6`
  - Example: theorem `...3rootspoly...`, text `ring`, fail `14`, pass `15`
  - Example: `mathd_numbertheory_202`, text `native_decide`, fail `11`, pass `16`

### 3) Gemini 2.5 Flash (`2026-02-15_043621Z...`)

- Samples: `6240`
- Verdicts: `6240`
- Missing verdicts: `0`
- Theorem rate distribution:
  - `0/32`: `174`
  - `16/32`: `7`
  - `32/32`: `14`
- Batch distribution:
  - `0/16`: `355`
  - `16/16`: `35`
- Binary-batch theorems: `195/195`
- Same-text pass/fail contradictions: `12`
  - Example: `mathd_algebra_547`, text `rw [h0, h1] norm_num`, fail `15`, pass `16`
  - Example: `mathd_numbertheory_101`, text `rfl`, fail `14`, pass `13`

## Interpretation

Across all three runs, every theorem with completed batches showed binary batch outcomes (`0/16` or `16/16`) only. That is exactly the failure mode expected from the known batch-diagnostics attribution bug in `src/proofconf/lean/verifier.py` (path normalization mismatch in `_extract_diagnostics`).

The identical-text pass/fail contradictions further confirm that verdict attribution is not reliable in these artifacts.

## Targeted Replay Checks (Patched Verifier)

Using the patched verifier, representative theorems were replayed from stored sample texts:

- Replay method note:
  - Original batch membership (`b0`/`b1`) was preserved from `source_path`.
  - Original in-batch ordering is not recoverable from artifacts, so exact per-sample flips are not expected to match 1:1.
  - The goal here is to test whether outcomes remain quantized/binary after patching.

### Replay of representative `16/32` theorem per model

- DeepSeek chat: `mathd_numbertheory_102` changed `16 -> 14`.
- DeepSeek reasoner: `mathd_numbertheory_202` changed `16 -> 30`.
- Gemini 2.5 Flash: `mathd_numbertheory_101` changed `16 -> 31`.

### Replay of representative `32/32` theorem per model

- DeepSeek chat: `mathd_numbertheory_81` changed `32 -> 0`.
- DeepSeek reasoner: `mathd_numbertheory_200` changed `32 -> 16`.
- Gemini 2.5 Flash: `mathd_numbertheory_200` stayed `32 -> 32`.

These checks confirm old theorem-level bins (`0/32`, `16/32`, `32/32`) are not trustworthy as reported.

## Conclusion

The previously observed quantized rates (`0`, `0.5`, `1`) are a pipeline artifact in these runs, not trustworthy model behavior. These three run artifacts should not be used for confidence/correctness correlation conclusions.

Use reruns with the patched verifier for any final correlation analysis.
