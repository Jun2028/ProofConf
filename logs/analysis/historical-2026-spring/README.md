# Recovered confidence results, April–May 2026

Recovered on 12 October 2026 from the earlier Hopper analysis workspace.
These results were missing from ProofConf's February repository snapshot.
The original reports, all their metric comparisons, and compact attempt-level
tables are retained here. This recovery makes no new model or Lean calls.

## The results above AUC 0.8

The [1 April note](2026-04-01-notes/20260401-proofconf-fixed-pool-followup.md)
reports these Goedel-Prover-V2-8B results on **`mathd_algebra_289` alone**:

| Metric | AUC |
| --- | ---: |
| Average trace confidence | 0.677419 |
| Lowest group confidence | **0.870968** |
| Bottom-10% group confidence | **0.838710** |
| Tail confidence | 0.580645 |

There were 32 attempts: one recorded correct proof and 31 failures. This theorem
was selected after inspecting an earlier corpus that stopped at the first
success. It is a single-theorem observation, not an independent benchmark-wide
result. The [earlier corpus report](2026-04-01-notes/20260401-proofconf-confidence-analysis.md)
and [early-stop clarification](2026-04-01-notes/20260423-early-stop-auc-clarification.md)
preserve that context.

The original generation logprobs and labels survived. The
[recovered table](2026-04-01-single-theorem/summary.json) reproduces all four
reported AUCs, using the original metric definitions, without regenerating or
reverifying any proof.

## Larger completed studies

| Study | Attempts | Highlighted metric | Global AUC | Mean within-theorem AUC |
| --- | ---: | --- | ---: | ---: |
| [Goedel fixed-32, completed 26 April](2026-04-26-goedel-fixed32/summary.md) | 7,808 | Lowest group confidence | **0.723530** | 0.515053 |
| [API proofs rescored on 25 May](2026-05-25-api-proof-rescoring/summary.md) | 35,749 | Minimum body-token logprob | **0.705206** | 0.517396 |
| Same May pool | 35,749 | Lowest-window body logprob | **0.661939** | 0.527688 |

The April study used Goedel-Prover-V2-8B generation scores on 244 MiniF2F
validation theorems, exactly 32 attempts each, with early stopping disabled.
It recorded 5,536 passing attempts and 205 solved theorems. Within-theorem AUC
averages over the 126 theorems containing both passing and failing attempts.
The archived operational failures remain failures, as in the original analysis.

The May pool contains **34,566 GPT-5.4 Mini attempts** (211 recorded passes) and
**1,183 DeepSeek V4 Flash attempts** (11 recorded passes). **Goedel-Prover-V2-8B
is the scorer**, teacher-forcing their reconstructed Lean proof bodies. These
are not GPT/DeepSeek's own generation-confidence scores. The pool covers 122
theorems, with 63 mixed-label theorems in the within-theorem calculation.
The [original audit](2026-05-25-api-proof-rescoring/original-audit.md) documents
duplicates, excluded environment failures, and the limits of the saved labels.

Global AUC pools all passing/failing attempt pairs. Within-theorem AUC first
compares attempts for the same theorem, then averages over eligible theorems.
Both give half credit to score ties. The positive global AUCs therefore do not,
on their own, establish useful ranking within a proof search or a repair gain.

## Metric definitions and reproduction

The April `paper_topk` score uses `C_t = -mean(top-k token logprobs)` with up to
20 returned entries per token. Full top-20 coverage was not required and there
was no fallback to chosen-token logprob. Window size is 24, stride 6, tail 256.
Lowest group is the minimum window mean; bottom-10% averages the lowest
`max(1, floor(0.1 * number_of_windows))` window means. The historical field
`avg_logprob` means average `C_t` in this mode, not average chosen-token logprob.
The implementation is already in
[`token_confidence.py`](../../../src/proofconf/metrics/token_confidence.py).

The May scores use chosen-token logprobs over the reconstructed proof body:
mean, minimum, bottom-10% token mean, minimum 24-token window mean (stride 6),
and mean of the last 256 tokens. Higher scores rank first in both archives.

Each dataset contains `summary.json` and `attempt_metrics.csv.gz`. Larger-study
summaries are unchanged copies. CSVs preserve every reported comparison metric and label
in original analysis order, with generator provenance added and raw text, private
file paths, and error dumps omitted. [provenance.json](provenance.json) records
original and archived hashes, source locations, and the single-theorem recovery.
The May archive follows the original JSONL order: the old presentation CSV had
reordered rows, which changes deterministic filtering when scores tie, although
it leaves AUC unchanged. No scores or labels were changed to resolve that difference.

From the repository root:

```bash
python3 scripts/verify_historical_results.py
```

This checks hashes, counts, global/within-theorem AUCs, point-biserial
correlations, and filtering tables using only the standard library. It verifies
the archived arithmetic, not the original top-k measurement quality or Lean
verdicts. No GPU, credentials, API access, or model download is needed.

## Still missing

The separate **2 April GPT-5.4 Mini prescreen** is referenced by
[ConfEvolve's original metric-sweep plan](https://github.com/Jun2028/ConfEvolve/blob/b3ffbb4/plan/2026-04-02_gpt54mini_metric_sweep_plan.md).
Its report was at
`ConfEvolve/logs/analysis/2026-04-02_gpt54mini_confidence_metric_analysis.md`
on Vanda. Neither that report nor its exact AUC table was recovered here;
Vanda SSH timed out on 12 October. The available Goedel and May rescoring
results above must not be substituted for that prescreen.
