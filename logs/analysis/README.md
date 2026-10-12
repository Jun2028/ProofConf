# Analysis Reports

This folder contains markdown reports derived from run outputs.

- [Recovered April–May 2026 confidence/AUC results](historical-2026-spring/README.md)
  include original reports and reproducible attempt-level tables.

- Use `plan/` for planning documents only.
- Use `logs/run/` for raw run logs and driver traces.
- Use `logs/analysis/` for human-readable run analyses and postmortems.

## Invalidation Notice (2026-02-15)

Several earlier reports are explicitly marked `[INVALIDATED on 2026-02-15]` because batched Lean verdict attribution was affected by the path-resolution bug documented in:

- `logs/analysis/2026-02-15_batch_verifier_diagnosis.md`
- `logs/analysis/2026-02-15_three_model_run_diagnosis.md`
