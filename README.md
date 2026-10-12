# ProofConf

The April–May 2026 experiments measuring whether predefined model-confidence
scores distinguish Lean proofs that pass verification from attempts that fail. Each experiment
keeps its producing code, inputs/configuration, results, and reproduction
instructions together.

## Experiments and evidence

| Experiment | Generator → scorer | Saved result | Scope |
| --- | --- | --- | --- |
| [Goedel confidence](experiments/goedel-confidence/) | Goedel-Prover-V2-8B → its generation top-20 logprobs | LGC AUC **0.723530** global, **0.515053** within theorem | April: 244 theorems × 32 attempts |
| [API-proof rescoring](experiments/api-proof-rescoring/) | GPT-5.4 Mini / DeepSeek V4 Flash → Goedel-Prover-V2-8B | Minimum-token AUC **0.705206** global, **0.517396** within theorem | May: 35,749 saved proof attempts |

The remembered **0.870968 / 0.838710 AUCs** are Goedel LGC / bottom-10%
scores on [one selected theorem](experiments/goedel-confidence/results/2026-04-01-single-theorem/summary.json),
with one passing and 31 failing attempts. They are an exploratory observation.
The larger April experiment supplies the fixed-budget comparison.

Global AUC compares passing and failing attempts across the entire pool.
Within-theorem AUC compares attempts on the same theorem, then averages over
theorems with both labels. Score ties receive half credit. These studies
measure correctness discrimination; they do not establish a proof-search or
repair benefit. Search experiments belong in [ConfEvolve](https://github.com/Jun2028/ConfEvolve).

## Scores

The April `paper_topk` method uses
`C_t = -mean(top-k candidate logprobs at token t)`, with up to 20 available
candidates. LGC is the minimum sliding-window mean; bottom-10% averages the
lowest `max(1, floor(0.1 × window_count))` window means. Windows contain 24
tokens with stride 6, including the final window; tail confidence uses the
last 256 tokens. The historical field `avg_logprob` contains **mean C_t** in
this mode. Full top-20 coverage was not required; chosen-token fallback was off.

The May experiment instead scores **chosen proof-body tokens** under Goedel:
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

The check calls the recovered analysis code for **all 13 metric comparisons**
across the three April/May datasets (43,589 rows), checking artifact hashes,
counts, AUCs, correlations, and filtering tables. It runs on CPU without model
calls or Lean. It does not revalidate the original logprobs or verification
labels.

Each experiment README gives the generation/scoring commands and required
external inputs. [Provenance](experiments/provenance.json) records source
locations, hashes, and the limited portability edits to recovered code. Large
raw model payloads and weights stay outside Git. Original reports and saved
scores retain their contents.

The separate **2 April GPT-5.4 Mini native-confidence prescreen** remains
unrecovered; May's Goedel rescoring must not be attributed to that experiment.
The older February pipeline, setup plans, invalidated reports, and cluster wrappers
are preserved in [the pre-cleanup history](https://github.com/Jun2028/ProofConf/commits/main).
