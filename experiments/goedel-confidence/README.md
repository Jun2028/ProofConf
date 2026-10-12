# Goedel generation confidence — April 2026

[Generation and Lean verification](scripts/eval_minif2f_passk.py) saves the
model's raw token logprobs and attempt verdicts. The original
[confidence analyzer](scripts/analyze_proofconf_confidence.py) computes
`paper_topk` scores and their relationship to those verdicts. These scripts
were recovered from the Hopper workspace that produced the results.

## Results

| Pool | Attempts | LGC global AUC | Mean within-theorem AUC |
| --- | ---: | ---: | ---: |
| [Selected `mathd_algebra_289`](results/2026-04-01-single-theorem/summary.json) | 32 | 0.870968 | 0.870968 (one theorem) |
| [Completed fixed-32 pool](results/2026-04-26-fixed32/summary.md) | 7,808 | 0.723530 | 0.515053 (126 mixed-label theorems) |

The single-theorem pool has one passing attempt and bottom-10% AUC 0.838710.
It was selected after observing an adaptive corpus that stopped at first
success. The [original April 1 observation](https://github.com/Jun2028/ProofConf/commits/main/logs/analysis/historical-2026-spring/2026-04-01-notes/20260401-proofconf-fixed-pool-followup.md)
is preserved in history. The single-theorem table was reconstructed on October
12 from the saved March token logprobs and labels, matching all four original AUCs.

The fixed pool covers all 244 MiniF2F validation theorems, exactly 32 attempts
each, with early stopping disabled: 5,536 passing attempts, 205 solved theorems.
Its 269 operational errors remain labeled as failures. Original summary files
and compressed attempt metrics sit beside one another under `results/`.
The root verifier checks every saved metric, including weak/negative ones.

## Produce the measurements

Run from the repository root. The generator needs `requests`, a running
Goedel-Prover-V2-8B chat-completions endpoint, MiniF2F validation JSONL, and a
shared Lean project with its dependencies installed. These are external inputs;
the script neither installs a model nor allocates GPUs.

```bash
python3 experiments/goedel-confidence/scripts/eval_minif2f_passk.py \
  --base-url http://127.0.0.1:8000/v1 --model Goedel-Prover-V2-8B \
  --data-path /path/to/miniF2F-lean4/data/valid.jsonl \
  --project-dir /path/to/shared/miniF2F-lean4 --output-dir runs/goedel/eval \
  --samples 32 --request-samples 16 --temperature 1.0 --top-p 0.95 \
  --max-tokens 40960 --max-model-len 40960 --prompt-headroom 1024 \
  --verify-mode subprocess --verify-timeout 300 \
  --enable-logprobs --top-logprobs 20 --disable-early-stop
python3 experiments/goedel-confidence/scripts/analyze_proofconf_confidence.py \
  --results-glob 'runs/goedel/eval/results.jsonl' --output-dir runs/goedel/analysis \
  --method paper_topk --top-k 20 --window-size 24 --stride 6 --tail-tokens 256 \
  --workers 1
```

The April jobs used four 61-theorem shards with these generation settings;
analysis accepts repeated `--results-glob` arguments. The effective generation
limit is 39,936 tokens after prompt headroom. No seed was recorded. Reanalysis
of the original run needs its saved `eval/results.jsonl` and `eval/raw/*.json`;
their source locations are in [provenance](../provenance.json). The compact
tables reproduce summary arithmetic without those large token payloads.
