from __future__ import annotations

from proofconf.pipeline.dataset import Problem


SYSTEM_PROMPT = (
    "You are a Lean 4 theorem prover. Return only Lean proof code. "
    "Do not include markdown fences, commentary, or the theorem statement. "
    "Never use sorry/admit."
)


def build_user_prompt(problem: Problem) -> str:
    return (
        "Complete the proof body for this Lean theorem. "
        "Output only the code that comes after ':= by'.\n\n"
        f"Informal statement:\n{problem.informal_prefix}\n\n"
        f"Lean context:\n{problem.header}\n{problem.formal_statement}"
    )
