## 2026-04-23 Early-stop/AUC clarification

- Checked `docs/work-log.md`, `docs/group-meeting-summary-2026-04-01.md`, and the evaluator scripts.
- Confirmed the completed `192 / 244` MiniF2F `pass@32` run with top-20 logprobs used adaptive early stopping: after a verified passing proof, the evaluator stopped generating/verifying further samples for that theorem unless `--disable-early-stop` was set.
- Clarified why global AUC over the full stored corpus is not a fair fixed-budget ProofConf experiment: solved/easy theorems contribute fewer attempts, while hard/unsolved theorems contribute many more failures, so the confidence-label distribution is entangled with the search policy.
- Clarified that the global AUC is still informative descriptively, but the fair experiment needs fixed theorem set, fixed attempts per theorem, token logprobs, full verification labels, and no early stop.
