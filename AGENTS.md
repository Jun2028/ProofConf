# ProofConf instructions

- Scope: predefined confidence metrics versus Lean proof correctness. Keep each
  experiment's code, configuration, results, and reproduction instructions in
  its directory under `experiments/`.
- Read the relevant experiment README before changes. Keep metric definitions,
  generator/scorer identity, and README claims consistent with the code.
- Preserve saved scores, labels, and original reports. Record sources and
  changes in `experiments/provenance.json`; retain negative results and caveats.
- Keep raw runs, credentials, model weights, caches, and operational logs out of
  Git. Put superseded material in Git history rather than active documentation.
- Before committing, follow [the commit policy](guidelines/git-commit.md).
- Use CPU for analysis, API calls, and Lean work. Reserve GPUs only for local
  model inference; the user's hard cap is two GPUs at any moment. Use a shared
  Lean/mathlib installation. This repository cleanup does not resume research.
- Validate changed paths and run `python3 scripts/verify_results.py`; for the
  prompt scorer, also run its existing tests as described in the root README.
