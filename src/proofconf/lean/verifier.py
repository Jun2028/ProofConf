from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from textwrap import indent
from time import sleep
from time import perf_counter
from typing import Dict, List, Sequence, Tuple


@dataclass
class VerifyResult:
    success: bool
    returncode: int
    elapsed_ms: int
    stdout: str
    stderr: str
    source_path: str


@dataclass(frozen=True)
class VerifyRequest:
    theorem_name: str
    header: str
    formal_statement: str
    proof_body: str
    sample_tag: str


@dataclass(frozen=True)
class _DiagnosticBlock:
    line: int
    level: str
    text: str


_DIAG_RE = re.compile(
    r"^(?P<path>.*?\.lean):(?P<line>\d+):(?P<col>\d+): "
    r"(?P<level>error|warning|information|info):(?P<message>.*)$"
)
_OPEN_FAIL_RE = re.compile(r"failed to open(?: file)? '([^']+)'")


def _extract_code_block(text: str) -> str:
    text = text.strip()
    if "```" not in text:
        return text
    parts = text.split("```")
    if len(parts) < 3:
        return text
    body = parts[1]
    lines = body.splitlines()
    if lines and lines[0].strip().startswith("lean"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def normalize_proof_body(raw_text: str) -> str:
    text = _extract_code_block(raw_text)

    if ":= by" in text:
        text = text.split(":= by", 1)[1]

    text = text.strip()
    if text.startswith("by"):
        text = text[2:].strip()

    return text.strip()


def _rename_theorem(formal_statement: str, suffix: str) -> str:
    lines = formal_statement.splitlines()
    if not lines:
        return formal_statement

    first = lines[0]
    m = re.match(r"^(\s*theorem\s+)(\S+)(.*)$", first)
    if m:
        lines[0] = f"{m.group(1)}{m.group(2)}_{suffix}{m.group(3)}"
    return "\n".join(lines) + ("\n" if formal_statement.endswith("\n") else "")


class LeanVerifier:
    def __init__(
        self,
        mini_f2f_root: Path,
        timeout_s: int = 45,
        lean_jobs: int | None = None,
        max_parallel_invocations: int | None = None,
    ):
        self.mini_f2f_root = mini_f2f_root
        self.timeout_s = timeout_s
        self.retry_count = int(os.environ.get("PROOFCONF_LEAN_RETRIES", "4"))
        self.retry_delay_s = float(os.environ.get("PROOFCONF_LEAN_RETRY_DELAY_S", "2.0"))
        if lean_jobs is None:
            jobs_text = (
                os.environ.get("PROOFCONF_LEAN_JOBS")
                or os.environ.get("LEAN_NUM_THREADS")
                or "1"
            )
            lean_jobs = int(jobs_text)
        self.lean_jobs = max(1, int(lean_jobs))
        if max_parallel_invocations is None:
            procs_text = os.environ.get("PROOFCONF_LAKE_MAX_PROCS", "4")
            max_parallel_invocations = int(procs_text)
        self.max_parallel_invocations = max(1, int(max_parallel_invocations))
        self._run_semaphore = threading.BoundedSemaphore(self.max_parallel_invocations)
        gap_ms_text = os.environ.get("PROOFCONF_LAKE_LAUNCH_GAP_MS", "250")
        try:
            gap_ms = float(gap_ms_text)
        except ValueError:
            gap_ms = 250.0
        self.launch_gap_s = max(0.0, gap_ms / 1000.0)
        self._launch_lock = threading.Lock()
        self._next_launch_at = 0.0
        keep_tmp_text = os.environ.get("PROOFCONF_KEEP_TMP", "").strip().lower()
        self.keep_tmp = keep_tmp_text in {"1", "true", "yes", "on"}
        prune_aesop_text = os.environ.get("PROOFCONF_PRUNE_AESOP_IMPORT", "1").strip().lower()
        self.prune_aesop_import = prune_aesop_text not in {"0", "false", "no", "off"}
        direct_lean_text = os.environ.get("PROOFCONF_DIRECT_LEAN", "1").strip().lower()
        self.use_direct_lean = direct_lean_text not in {"0", "false", "no", "off"}
        self._lean_env = self._resolve_lean_env() if self.use_direct_lean else None
        self._lean_cmd = ["lean"] if self._lean_env is not None else ["lake", "env", "lean"]
        tmp_root = os.environ.get("PROOFCONF_TMP_ROOT", "").strip()
        if tmp_root:
            self.tmp_dir = Path(tmp_root).expanduser().resolve()
        else:
            self.tmp_dir = mini_f2f_root / ".proofconf_tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_lean_env(self) -> dict | None:
        try:
            proc = subprocess.run(
                ["lake", "env", "printenv"],
                cwd=self.mini_f2f_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if proc.returncode != 0:
            return None

        env = os.environ.copy()
        for line in proc.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                continue
            env[key] = value
        return env

    def _reserve_launch_slot(self) -> None:
        if self.launch_gap_s <= 0.0:
            return
        while True:
            wait_s = 0.0
            with self._launch_lock:
                now = perf_counter()
                if now >= self._next_launch_at:
                    self._next_launch_at = now + self.launch_gap_s
                    return
                wait_s = self._next_launch_at - now
            sleep(wait_s)

    def _cleanup_source(self, source_path: Path) -> None:
        if self.keep_tmp:
            return
        try:
            source_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _uses_aesop(proof_text: str) -> bool:
        return re.search(r"\baesop\b", proof_text.lower()) is not None

    def _effective_header(self, header: str, proof_texts: Sequence[str]) -> str:
        if not self.prune_aesop_import:
            return header
        if "import Aesop" not in header:
            return header
        if any(self._uses_aesop(text) for text in proof_texts):
            return header

        lines = [line for line in header.splitlines() if line.strip() != "import Aesop"]
        if not lines:
            return ""
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _is_transient_fd_error(stdout: str, stderr: str) -> bool:
        text = f"{stdout}\n{stderr}"
        lower = text.lower()
        if "too many open files in system" in lower:
            return True

        for match in _OPEN_FAIL_RE.finditer(text):
            path_text = match.group(1)
            try:
                if Path(path_text).exists():
                    return True
            except OSError:
                continue
        return False

    def _run_lean(self, source_path: Path) -> subprocess.CompletedProcess[str]:
        with self._run_semaphore:
            self._reserve_launch_slot()
            return subprocess.run(
                [*self._lean_cmd, "-E", "warning", "-j", str(self.lean_jobs), str(source_path)],
                cwd=self.mini_f2f_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                env=self._lean_env,
            )

    def verify(
        self,
        theorem_name: str,
        header: str,
        formal_statement: str,
        proof_body: str,
        sample_tag: str,
    ) -> VerifyResult:
        normalized = normalize_proof_body(proof_body)
        statement = _rename_theorem(formal_statement, sample_tag)
        effective_header = self._effective_header(header, [normalized])

        if not normalized:
            normalized = "admit"

        source = (
            effective_header
            + "\n"
            + statement
            + "\n"
            + indent(normalized, "  ")
            + "\n"
        )

        source_path = self.tmp_dir / f"{theorem_name}_{sample_tag}.lean"
        source_path.write_text(source, encoding="utf-8")

        start = perf_counter()
        retries_used = 0
        try:
            for attempt in range(self.retry_count + 1):
                try:
                    proc = self._run_lean(source_path)
                except subprocess.TimeoutExpired as exc:
                    elapsed_ms = int((perf_counter() - start) * 1000)
                    return VerifyResult(
                        success=False,
                        returncode=124,
                        elapsed_ms=elapsed_ms,
                        stdout=(exc.stdout or ""),
                        stderr=(exc.stderr or "") + "\n[proofconf] Lean verification timed out.\n",
                        source_path=str(source_path),
                    )

                if proc.returncode != 0 and attempt < self.retry_count and self._is_transient_fd_error(proc.stdout, proc.stderr):
                    retries_used += 1
                    sleep(self.retry_delay_s * (attempt + 1))
                    continue

                elapsed_ms = int((perf_counter() - start) * 1000)
                stderr_text = proc.stderr
                if retries_used > 0:
                    stderr_text = f"{stderr_text}\n[proofconf] retried {retries_used} time(s) after transient fd exhaustion.\n"
                return VerifyResult(
                    success=proc.returncode == 0,
                    returncode=proc.returncode,
                    elapsed_ms=elapsed_ms,
                    stdout=proc.stdout,
                    stderr=stderr_text,
                    source_path=str(source_path),
                )

            elapsed_ms = int((perf_counter() - start) * 1000)
            return VerifyResult(
                success=False,
                returncode=1,
                elapsed_ms=elapsed_ms,
                stdout="",
                stderr="[proofconf] Unexpected verifier fallthrough.\n",
                source_path=str(source_path),
            )
        finally:
            self._cleanup_source(source_path)

    def verify_many(self, requests: Sequence[VerifyRequest], batch_tag: str) -> List[VerifyResult]:
        if not requests:
            return []

        first = requests[0]
        homogeneous = all(
            req.header == first.header
            and req.formal_statement == first.formal_statement
            and req.theorem_name == first.theorem_name
            for req in requests
        )
        if not homogeneous:
            return [
                self.verify(
                    theorem_name=req.theorem_name,
                    header=req.header,
                    formal_statement=req.formal_statement,
                    proof_body=req.proof_body,
                    sample_tag=req.sample_tag,
                )
                for req in requests
            ]

        normalized_rows = [normalize_proof_body(req.proof_body) for req in requests]
        effective_header = self._effective_header(first.header, normalized_rows)
        source, ranges = self._build_batch_source(effective_header, first.formal_statement, list(requests))
        source_path = self.tmp_dir / f"{first.theorem_name}_{batch_tag}.lean"
        source_path.write_text(source, encoding="utf-8")

        start = perf_counter()
        retries_used = 0
        try:
            for attempt in range(self.retry_count + 1):
                try:
                    proc = self._run_lean(source_path)
                except subprocess.TimeoutExpired as exc:
                    elapsed_ms = int((perf_counter() - start) * 1000)
                    timeout_stderr = (exc.stderr or "") + "\n[proofconf] Lean verification timed out.\n"
                    return [
                        VerifyResult(
                            success=False,
                            returncode=124,
                            elapsed_ms=elapsed_ms,
                            stdout=(exc.stdout or ""),
                            stderr=timeout_stderr,
                            source_path=str(source_path),
                        )
                        for _ in requests
                    ]

                if proc.returncode != 0 and attempt < self.retry_count and self._is_transient_fd_error(proc.stdout, proc.stderr):
                    retries_used += 1
                    sleep(self.retry_delay_s * (attempt + 1))
                    continue
                break

            elapsed_ms = int((perf_counter() - start) * 1000)
            if retries_used > 0:
                proc = subprocess.CompletedProcess(
                    args=proc.args,
                    returncode=proc.returncode,
                    stdout=proc.stdout,
                    stderr=f"{proc.stderr}\n[proofconf] retried {retries_used} time(s) after transient fd exhaustion.\n",
                )

            if proc.returncode == 0:
                return [
                    VerifyResult(
                        success=True,
                        returncode=0,
                        elapsed_ms=elapsed_ms,
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        source_path=str(source_path),
                    )
                    for _ in requests
                ]

            diagnostics = self._extract_diagnostics(
                source_path=source_path,
                text=f"{proc.stderr}\n{proc.stdout}",
            )
            if not diagnostics:
                return [
                    VerifyResult(
                        success=False,
                        returncode=proc.returncode,
                        elapsed_ms=elapsed_ms,
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        source_path=str(source_path),
                    )
                    for _ in requests
                ]

            per_index: Dict[int, List[str]] = {i: [] for i in range(len(requests))}
            global_errors: List[str] = []
            for block in diagnostics:
                if block.level != "error":
                    continue
                matched = False
                for idx, (start_line, end_line) in enumerate(ranges):
                    if start_line <= block.line <= end_line:
                        per_index[idx].append(block.text)
                        matched = True
                        break
                if not matched:
                    global_errors.append(block.text)

            results: List[VerifyResult] = []
            for idx in range(len(requests)):
                errors = global_errors + per_index[idx]
                is_success = len(errors) == 0
                results.append(
                    VerifyResult(
                        success=is_success,
                        returncode=0 if is_success else 1,
                        elapsed_ms=elapsed_ms,
                        stdout="",
                        stderr="\n\n".join(errors),
                        source_path=str(source_path),
                    )
                )
            return results
        finally:
            self._cleanup_source(source_path)

    def _build_batch_source(
        self,
        header: str,
        formal_statement: str,
        requests: List[VerifyRequest],
    ) -> Tuple[str, List[Tuple[int, int]]]:
        lines: List[str] = []
        header_text = header.strip()
        if header_text:
            lines.extend(header_text.splitlines())
            lines.append("")

        ranges: List[Tuple[int, int]] = []
        for req in requests:
            normalized = normalize_proof_body(req.proof_body) or "admit"
            statement = _rename_theorem(formal_statement, req.sample_tag).strip()

            start_line = len(lines) + 1
            lines.extend(statement.splitlines())
            lines.extend(indent(normalized, "  ").splitlines())
            end_line = len(lines)
            ranges.append((start_line, end_line))
            lines.append("")

        source = "\n".join(lines).rstrip() + "\n"
        return source, ranges

    def _extract_diagnostics(self, source_path: Path, text: str) -> List[_DiagnosticBlock]:
        target = source_path.resolve()
        blocks: List[_DiagnosticBlock] = []
        current: _DiagnosticBlock | None = None
        current_lines: List[str] = []

        def flush() -> None:
            nonlocal current, current_lines
            if current is not None:
                blocks.append(
                    _DiagnosticBlock(
                        line=current.line,
                        level=current.level,
                        text="\n".join(current_lines).strip(),
                    )
                )
            current = None
            current_lines = []

        for raw_line in text.splitlines():
            m = _DIAG_RE.match(raw_line)
            if m:
                flush()
                path_text = m.group("path")
                diag_path = Path(path_text)
                if not diag_path.is_absolute():
                    diag_path = self.mini_f2f_root / diag_path
                # Normalize absolute/relative diagnostics through resolve() so
                # symlinked paths (e.g. /nfs/... vs /scratch/...) still match.
                try:
                    diag_path = diag_path.resolve()
                except FileNotFoundError:
                    diag_path = diag_path.absolute()
                if diag_path != target:
                    continue
                current = _DiagnosticBlock(
                    line=int(m.group("line")),
                    level=m.group("level"),
                    text=raw_line.strip(),
                )
                current_lines = [raw_line.strip()]
            elif current is not None:
                current_lines.append(raw_line.rstrip())

        flush()
        return blocks
