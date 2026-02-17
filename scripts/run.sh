#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${1:-configs/initial_run.json}"
RUN_TAG="${2:-initial}"

uv run python -m proofconf.pipeline.run_experiment --config "$CONFIG_PATH" --tag "$RUN_TAG"
