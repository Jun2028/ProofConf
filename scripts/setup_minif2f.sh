#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="$ROOT_DIR/datasets/miniF2F/raw"
ZIP_PATH="$ROOT_DIR/miniF2F-lean4-main.zip"
PROJECT_DIR="$RAW_DIR/miniF2F-lean4-main"
CACHE_ROOT="${PROOFCONF_CACHE_ROOT:-/scratch/${USER}/data/proofconf/cache}"
USE_CACHE="${PROOFCONF_USE_LAKE_CACHE:-1}"
RUN_FULL_BUILD="${PROOFCONF_RUN_LAKE_BUILD:-0}"

mkdir -p "$RAW_DIR"
mkdir -p "$CACHE_ROOT"

if [ ! -d "$PROJECT_DIR" ]; then
  unzip -q "$ZIP_PATH" -d "$RAW_DIR"
fi

cd "$PROJECT_DIR"
# Fix TLS trust for the cache downloader in this environment.
export XDG_CACHE_HOME="$CACHE_ROOT"
export SSL_CERT_FILE="${SSL_CERT_FILE:-/etc/ssl/cert.pem}"
export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-$SSL_CERT_FILE}"

if [ "$USE_CACHE" = "1" ]; then
  if ! lake exe cache get; then
    echo "[warn] lake cache download failed; continuing with source build." >&2
  fi
fi

if [ "$RUN_FULL_BUILD" = "1" ]; then
  LEAN_THREADS="${PROOFCONF_LEAN_THREADS:-2}"
  LEAN_NUM_THREADS="$LEAN_THREADS" lake build
fi
