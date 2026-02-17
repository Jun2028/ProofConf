from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence


@dataclass
class Problem:
    theorem_name: str
    split: str
    difficulty: float
    difficulty_level: str
    informal_prefix: str
    header: str
    formal_statement: str


def load_problems(
    dataset_json: str | Path,
    difficulty_levels: Sequence[str],
    split: str,
    limit: int,
) -> List[Problem]:
    rows = json.loads(Path(dataset_json).read_text(encoding="utf-8"))
    selected: List[Problem] = []

    for row in rows:
        level = row.get("Difficulty Gading", "")
        row_split = row.get("Split", "")
        if level not in difficulty_levels:
            continue
        if split and row_split != split:
            continue
        selected.append(
            Problem(
                theorem_name=row["Theorem Name"],
                split=row_split,
                difficulty=float(row.get("Difficulty", 0.0)),
                difficulty_level=level,
                informal_prefix=row.get("Informal Prefix", ""),
                header=row["Header"],
                formal_statement=row["Formal Statement"],
            )
        )

    selected.sort(key=lambda p: (p.difficulty, p.theorem_name))
    return selected[:limit]
