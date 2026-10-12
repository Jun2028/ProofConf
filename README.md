# ProofConf

ProofConf studies whether a language model's token-level confidence can
distinguish Lean proof attempts that pass verification from those that fail.
It evaluates predefined scores—such as the confidence of the weakest token
window—against saved Lean verification outcomes.

The repository includes proof generation, confidence scoring, analysis code,
and attempt-level results. It covers **Goedel-Prover-V2-8B's own generations**
and **GPT-5.4 Mini / DeepSeek V4 Flash proofs rescored by Goedel**. Each study
keeps its code and results together, with commands for reproducing the analysis.

## Results

| Proof pool | Confidence metric | Global AUC | Mean within-theorem AUC |
| --- | --- | ---: | ---: |
| [Goedel: `mathd_algebra_289`, 32 attempts](experiments/goedel-confidence/results/2026-04-01-single-theorem/summary.json) | Lowest group confidence (LGC) | **0.870968** | 0.870968 (one theorem) |
| Same single-theorem pool | Bottom-10% group confidence | **0.838710** | 0.838710 (one theorem) |
| [Goedel: 244 theorems × 32 attempts](experiments/goedel-confidence/results/2026-04-26-fixed32/summary.md) | LGC | **0.723530** | 0.515053 |
| [GPT / DeepSeek: 35,749 attempts](experiments/api-proof-rescoring/results/2026-05-25/summary.md) | Minimum body-token logprob under Goedel | **0.705206** | 0.517396 |

The **0.871 and 0.839 AUCs** come from an exploratory single-theorem case with
**one passing and 31 failing attempts**, selected after inspecting a corpus
that stopped at the first success. The larger Goedel study uses a fixed budget
of 32 attempts per theorem. Its weaker within-theorem result limits how far the
single-theorem finding can be generalized. The linked summaries include every
measured score, including those below AUC 0.5.

Global AUC compares passing and failing attempts across the entire pool.
Within-theorem AUC compares attempts on the same theorem, then averages over
theorems with both labels. Score ties receive half credit. These studies
measure correctness discrimination; they do not establish a proof-search or
repair benefit. Related proof-search work is in [ConfEvolve](https://github.com/Jun2028/ConfEvolve).

## Experiments

- **[Goedel generation confidence](experiments/goedel-confidence/):** generate
  proof attempts, save top-20 token logprobs, verify with a shared Lean project,
  and compare confidence with verification outcomes.
- **[GPT / DeepSeek proof rescoring](experiments/api-proof-rescoring/):**
  reconstruct 34,566 GPT-5.4 Mini and 1,183 DeepSeek V4 Flash proof attempts
  from saved traces, then score their proof bodies with Goedel. The API models
  are the generators; Goedel is the confidence scorer. Their native-confidence
  benchmark results are not included in the current tables.

## Scores

The generation-confidence study's `paper_topk` method uses
`C_t = -mean(top-k candidate logprobs at token t)`, with up to 20 available
candidates. LGC is the minimum sliding-window mean; bottom-10% averages the
lowest `max(1, floor(0.1 × window_count))` window means. Windows contain 24
tokens with stride 6, including the final window; tail confidence uses the
last 256 tokens. The historical field `avg_logprob` contains **mean C_t** in
this mode. Full top-20 coverage was not required; chosen-token fallback was off.

The API-proof study scores **chosen proof-body tokens** under Goedel:
mean, minimum, bottom-10% token mean, minimum window mean, and tail mean.
Those are external scores of API-generated proofs. Each experiment's source
implements its recorded definition. All reported AUCs use higher scores
as the positive direction, including results below 0.5.

## Reproduce the saved tables

Python 3.10+:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/verify_results.py
python3 -m unittest discover -s experiments/api-proof-rescoring/tests
```

The check calls each experiment's analysis code for **all 13 metric comparisons**
across the three saved datasets (43,589 rows), checking artifact hashes,
counts, AUCs, correlations, and filtering tables. It runs on CPU without model
calls or Lean. It does not revalidate the original logprobs or verification
labels.

Each experiment README gives the generation/scoring commands and required
external inputs. [Provenance](experiments/provenance.json) records source
locations, hashes, and the limited portability edits to the original code. Large
raw model payloads and weights stay outside Git. Scores and labels retain their
original values; personal filesystem paths in metadata are redacted.

The saved labels retain the original studies' limitations: the fixed Goedel
pool counts operational errors as failures; the API pool contains duplicates
and uses trace labels without fresh Lean verification. See the experiment
READMEs and the [API-pool audit](experiments/api-proof-rescoring/results/2026-05-25/original-audit.md)
for details. Earlier implementations and superseded material remain available
in [repository history](https://github.com/Jun2028/ProofConf/commits/main).
