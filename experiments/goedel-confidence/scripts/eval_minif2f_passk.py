#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

import requests


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def remove_comments(text: str) -> str:
    text = re.sub(r"/-.*?-/", "", text, flags=re.DOTALL)
    cleaned_lines = []
    for line in text.splitlines():
        cleaned_lines.append(line.split("--", 1)[0])
    return "\n".join(cleaned_lines).strip()


def return_theorem_to_prove(text: str):
    match = re.search(r"((?:theorem).*?:=\s*by\s*sorry)", text, re.DOTALL)
    return match.span() if match else None


def return_theorem_to_replace(text: str):
    match = re.search(r"((?:^|\s)theorem\s+.*?:=\s*by)", text, re.DOTALL)
    return match.span() if match else None


def replace_statement_in_proof(statement: str, proof: str) -> str:
    if "apply?" in proof or "exact?" in proof:
        raise ValueError("Generated proof uses forbidden suggestion tactics.")
    statement_clean = remove_comments(statement)
    statement_span = return_theorem_to_prove(statement_clean)
    if statement_span is None:
        raise ValueError("Could not find theorem statement ending with ':= by sorry'.")
    proof_clean = remove_comments(proof)
    proof_span = return_theorem_to_replace(proof_clean)
    if proof_span is None:
        raise ValueError("Could not find theorem body in generated proof.")
    return statement_clean[: statement_span[1]].replace("sorry", "") + proof_clean[proof_span[1] :]


def extract_code_block(text: str):
    for pattern in (
        r"```lean4\n(.*?)\n```",
        r"```lean4\n(.*?)```",
        r"```lean\n(.*?)```",
    ):
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[-1]
    return None


def build_problem_code(row: dict) -> str:
    header = row.get("header", "")
    statement = row["formal_statement"].split(":= by")[0] + ":= by sorry"
    return f"{header}{statement}"


def build_prompt(row: dict) -> str:
    statement = build_problem_code(row)
    return (
        "Complete the following Lean 4 code:\n\n"
        f"```lean4\n{statement}```\n\n"
        "Before producing the Lean 4 code to formally prove the given theorem, "
        "provide a detailed proof plan outlining the main proof steps and strategies.\n"
        "The plan should highlight key ideas, intermediate lemmas, and proof structures "
        "that will guide the construction of the final formal proof."
    )


def verify_file(project_dir: Path, file_path: Path, timeout: int) -> dict:
    lake_bin = str(Path("~/.elan/bin/lake").expanduser())
    text = file_path.read_text(encoding="utf-8")
    result = {
        "file": str(file_path),
        "forbidden_shortcuts": any(token in text for token in ("sorry", "admit")),
    }
    completed = subprocess.run(
        [lake_bin, "env", "lean", str(file_path)],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result["returncode"] = completed.returncode
    result["stdout"] = completed.stdout
    result["stderr"] = completed.stderr
    result["passed"] = completed.returncode == 0 and not result["forbidden_shortcuts"]
    return result


def build_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def request_samples(
    *,
    base_url,
    api_key,
    model,
    prompt,
    request_samples,
    temperature,
    top_p,
    max_tokens,
    max_model_len,
    prompt_headroom,
    seed,
    enable_logprobs,
    top_logprobs,
):
    effective_max_tokens = max_tokens
    if max_model_len is not None and prompt_headroom is not None:
        effective_max_tokens = min(effective_max_tokens, max(1, max_model_len - prompt_headroom))
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "n": request_samples,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": effective_max_tokens,
    }
    if enable_logprobs:
        payload["logprobs"] = True
        if top_logprobs > 0:
            payload["top_logprobs"] = top_logprobs
    if seed is not None:
        payload["seed"] = seed
    response = requests.post(
        build_chat_completions_url(base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=7200,
    )
    response.raise_for_status()
    return response.json()


def append_jsonl(path: Path, payload: dict):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", default="dummy")
    parser.add_argument("--model", required=True)
    parser.add_argument("--data-path", required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--request-samples", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--max-tokens", type=int, default=40960)
    parser.add_argument("--max-model-len", type=int, default=40960)
    parser.add_argument("--prompt-headroom", type=int, default=1024)
    parser.add_argument("--verify-timeout", type=int, default=300)
    parser.add_argument("--verify-mode", choices=("subprocess", "none"), default="subprocess")
    parser.add_argument("--disable-early-stop", action="store_true")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--enable-logprobs", action="store_true")
    parser.add_argument("--top-logprobs", type=int, default=0)
    args = parser.parse_args()

    data_path = Path(args.data_path).resolve()
    project_dir = Path(args.project_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    proofs_dir = output_dir / "proofs"
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    proofs_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.json"
    results_path = output_dir / "results.jsonl"

    processed = {}
    if results_path.exists():
        for row in load_jsonl(results_path):
            processed[row["name"]] = row

    rows = list(load_jsonl(data_path))
    if args.limit is not None:
        rows = rows[: args.limit]

    solved = sum(1 for row in processed.values() if row.get("solved"))
    total = len(processed)
    started_at = time.time()

    for row_index, row in enumerate(rows):
        name = row["name"]
        if name in processed:
            continue

        base_problem_code = build_problem_code(row)
        prompt = build_prompt(row)
        target_dir = proofs_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)

        raw_payloads = []
        generated = []
        verification_records = []
        solved_this_problem = False
        raw_payload_path = raw_dir / f"{name}.json"
        sample_index = 0

        while sample_index < args.samples and (
            args.disable_early_stop or args.verify_mode == "none" or not solved_this_problem
        ):
            current_n = min(args.request_samples, args.samples - sample_index)
            payload = request_samples(
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                prompt=prompt,
                request_samples=current_n,
                temperature=args.temperature,
                top_p=args.top_p,
                max_tokens=args.max_tokens,
                max_model_len=args.max_model_len,
                prompt_headroom=args.prompt_headroom,
                seed=None if args.seed is None else args.seed + sample_index,
                enable_logprobs=args.enable_logprobs,
                top_logprobs=args.top_logprobs,
            )
            raw_payloads.append(payload)
            raw_payload_path.write_text(
                json.dumps(raw_payloads, indent=2),
                encoding="utf-8",
            )
            for choice in payload["choices"]:
                text = choice["message"]["content"]
                generated.append(text)
                candidate_record = {
                    "index": sample_index,
                    "raw_text": text,
                }
                sample_index += 1
                try:
                    extracted = extract_code_block(text)
                    if not extracted:
                        raise ValueError("No Lean code block found in model output.")
                    full_code = replace_statement_in_proof(base_problem_code, extracted)
                    candidate_file = target_dir / f"{candidate_record['index']:02d}.lean"
                    candidate_file.write_text(full_code + "\n", encoding="utf-8")
                    candidate_record["file"] = str(candidate_file)
                    if args.verify_mode == "subprocess":
                        verification = verify_file(project_dir, candidate_file, args.verify_timeout)
                        candidate_record["verification"] = verification
                        if verification["passed"]:
                            solved_this_problem = True
                    else:
                        candidate_record["verification"] = None
                except Exception as exc:  # noqa: BLE001
                    candidate_record["error"] = repr(exc)
                verification_records.append(candidate_record)
                if solved_this_problem and args.verify_mode == "subprocess" and not args.disable_early_stop:
                    break

        if args.verify_mode == "none":
            solved_this_problem = False

        total += 1
        if solved_this_problem:
            solved += 1

        result = {
            "name": name,
            "row_index": row_index,
            "solved": solved_this_problem,
            "samples_requested": args.samples,
            "samples_generated": len(generated),
            "verification_records": verification_records,
            "verify_mode": args.verify_mode,
        }
        append_jsonl(results_path, result)

        summary = {
            "solved": solved,
            "total": total,
            "pass_at_k": solved / total if total else 0.0,
            "samples": args.samples,
            "request_samples": args.request_samples,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "max_tokens": args.max_tokens,
            "max_model_len": args.max_model_len,
            "prompt_headroom": args.prompt_headroom,
            "effective_max_tokens": min(args.max_tokens, max(1, args.max_model_len - args.prompt_headroom)),
            "verify_mode": args.verify_mode,
            "early_stop_enabled": args.verify_mode == "subprocess" and not args.disable_early_stop,
            "enable_logprobs": args.enable_logprobs,
            "top_logprobs": args.top_logprobs,
            "elapsed_seconds": round(time.time() - started_at, 2),
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps({"name": name, "solved": solved_this_problem, **summary}, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
