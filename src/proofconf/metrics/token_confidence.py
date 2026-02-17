from __future__ import annotations

from bisect import bisect_right
from math import exp
from typing import Dict, List, Sequence, Tuple


def chosen_token_scores(logprobs: List[float], use_probability: bool = False) -> List[float]:
    if use_probability:
        return [exp(lp) for lp in logprobs]
    return logprobs


def paper_token_confidence_at_t(
    candidate_logprobs: Sequence[float],
    top_k: int,
    require_full_topk: bool = False,
) -> float:
    # Eq. (2) from DeepConf: C_t = - mean(log P_t(j)) over top-k tokens.
    k = max(1, int(top_k))
    ordered = sorted((float(x) for x in candidate_logprobs), reverse=True)
    use = ordered[:k]
    if not use:
        return float("nan")
    if require_full_topk and len(use) < k:
        return float("nan")
    return -(sum(use) / len(use))


def token_confidence_series(
    chosen_logprobs: Sequence[float],
    top_logprobs: Sequence[Sequence[float]],
    method: str = "paper_topk",
    top_k: int = 20,
    require_full_topk: bool = False,
    fallback_to_chosen: bool = False,
) -> List[float]:
    if method == "chosen_logprob":
        return [float(x) for x in chosen_logprobs]

    if method != "paper_topk":
        raise ValueError(f"Unsupported token confidence method: {method}")

    aligned = min(len(chosen_logprobs), len(top_logprobs))
    if aligned <= 0:
        return []

    out: List[float] = []
    for idx in range(aligned):
        cands = list(top_logprobs[idx])
        score = paper_token_confidence_at_t(
            candidate_logprobs=cands,
            top_k=top_k,
            require_full_topk=require_full_topk,
        )
        if score != score:  # NaN check
            if fallback_to_chosen:
                out.append(-float(chosen_logprobs[idx]))
                continue
            return []
        out.append(score)
    return out


def sliding_window_ranges(length: int, window_size: int, stride: int) -> List[Tuple[int, int]]:
    if length <= 0:
        return []

    size = max(1, window_size)
    step = max(1, stride)

    if length <= size:
        return [(0, length)]

    ranges: List[Tuple[int, int]] = []
    i = 0
    while i + size <= length:
        ranges.append((i, i + size))
        i += step

    if (length - size) % step != 0:
        ranges.append((length - size, length))

    return ranges


def sliding_window_means(values: List[float], window_size: int, stride: int) -> List[float]:
    if not values:
        return []
    windows: List[float] = []
    for start, end in sliding_window_ranges(len(values), window_size, stride):
        chunk = values[start:end]
        windows.append(sum(chunk) / len(chunk))
    return windows


def average_trace_confidence(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def group_confidence_scores(values: List[float], window_size: int, stride: int) -> List[float]:
    return sliding_window_means(values, window_size, stride)


def lowest_group_confidence(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    return min(values)


def bottom_percent_group_confidence(values: Sequence[float], fraction: float = 0.1) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    n = max(1, int(len(ordered) * max(0.0, min(1.0, fraction))))
    bottom = ordered[:n]
    return sum(bottom) / len(bottom)


def tail_confidence_score(values: Sequence[float], tail_tokens: int) -> float:
    if not values:
        return float("nan")
    tail_n = min(len(values), max(1, int(tail_tokens)))
    tail = list(values)[-tail_n:]
    return sum(tail) / len(tail)


def confidence_metrics(
    token_scores: List[float],
    window_size: int,
    stride: int,
    tail_tokens: int = 256,
) -> Dict[str, float]:
    if not token_scores:
        return {
            "avg_logprob": float("nan"),
            "lowest_group_confidence": float("nan"),
            "bottom10_group_confidence": float("nan"),
            "tail_confidence": float("nan"),
            "token_count": 0,
            "window_count": 0,
        }

    windows = group_confidence_scores(token_scores, window_size, stride)

    return {
        # Kept for backward compatibility in downstream summaries; this is now
        # "average trace confidence" when paper_topk mode is used.
        "avg_logprob": average_trace_confidence(token_scores),
        "lowest_group_confidence": lowest_group_confidence(windows),
        "bottom10_group_confidence": bottom_percent_group_confidence(windows, fraction=0.1),
        "tail_confidence": tail_confidence_score(token_scores, tail_tokens),
        "token_count": len(token_scores),
        "window_count": len(windows),
    }


def _line_starts(text: str) -> List[int]:
    starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            starts.append(idx + 1)
    return starts


def _char_to_line(line_starts: List[int], pos: int) -> int:
    idx = bisect_right(line_starts, max(0, pos)) - 1
    return max(1, idx + 1)


def _trim_segment(text: str, start: int, end: int) -> Tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _is_structure_segment(segment: str) -> bool:
    s = segment.strip()
    if not s:
        return True
    if s.startswith("--"):
        return True
    if s in {"by", "·", "|"}:
        return True
    if s.startswith("case "):
        return True
    return False


def split_tactic_segments(text: str) -> List[Tuple[int, int]]:
    # Split on top-level ';' and newline; ignore delimiters inside comments/strings/brackets.
    segments: List[Tuple[int, int]] = []
    start = 0
    i = 0
    n = len(text)
    paren = 0
    bracket = 0
    brace = 0
    in_string = False
    escape = False
    block_comment = 0
    line_comment = False

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment > 0:
            if ch == "/" and nxt == "-":
                block_comment += 1
                i += 2
                continue
            if ch == "-" and nxt == "/":
                block_comment -= 1
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "\"":
                in_string = False
            i += 1
            continue

        if ch == "-" and nxt == "-":
            line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "-":
            block_comment = 1
            i += 2
            continue
        if ch == "\"":
            in_string = True
            i += 1
            continue

        if ch == "(":
            paren += 1
        elif ch == ")" and paren > 0:
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]" and bracket > 0:
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}" and brace > 0:
            brace -= 1

        at_top = paren == 0 and bracket == 0 and brace == 0
        if at_top and (ch == ";" or ch == "\n"):
            seg_start, seg_end = _trim_segment(text, start, i)
            if seg_end > seg_start:
                segment = text[seg_start:seg_end]
                if not _is_structure_segment(segment):
                    segments.append((seg_start, seg_end))
            start = i + 1
        i += 1

    seg_start, seg_end = _trim_segment(text, start, n)
    if seg_end > seg_start:
        segment = text[seg_start:seg_end]
        if not _is_structure_segment(segment):
            segments.append((seg_start, seg_end))

    return segments


def weakest_span_annotation(
    tokens: Sequence[str],
    logprobs: Sequence[float],
    window_size: int,
    stride: int,
    neighborhood_lines: int = 2,
) -> Dict[str, object]:
    aligned_len = min(len(tokens), len(logprobs))
    if aligned_len <= 0:
        return {
            "weakest_window_start_token": None,
            "weakest_window_end_token": None,
            "weakest_window_start_line": None,
            "weakest_window_end_line": None,
            "weakest_context_start_line": None,
            "weakest_context_end_line": None,
            "weakest_excerpt": "",
            "tactic_segmentation_used": False,
            "weakest_tactic_index_start": None,
            "weakest_tactic_index_end": None,
        }

    token_list = list(tokens[:aligned_len])
    score_list = list(logprobs[:aligned_len])

    window_ranges = sliding_window_ranges(aligned_len, window_size, stride)
    if not window_ranges:
        return {
            "weakest_window_start_token": None,
            "weakest_window_end_token": None,
            "weakest_window_start_line": None,
            "weakest_window_end_line": None,
            "weakest_context_start_line": None,
            "weakest_context_end_line": None,
            "weakest_excerpt": "",
            "tactic_segmentation_used": False,
            "weakest_tactic_index_start": None,
            "weakest_tactic_index_end": None,
        }

    window_means: List[float] = []
    for start, end in window_ranges:
        chunk = score_list[start:end]
        window_means.append(sum(chunk) / len(chunk))
    weak_idx = min(range(len(window_means)), key=lambda i: window_means[i])
    weak_tok_start, weak_tok_end = window_ranges[weak_idx]

    text = "".join(token_list)
    offsets: List[Tuple[int, int]] = []
    cursor = 0
    for tok in token_list:
        start = cursor
        cursor += len(tok)
        offsets.append((start, cursor))

    weak_char_start = offsets[weak_tok_start][0]
    weak_char_end = offsets[max(weak_tok_start, weak_tok_end - 1)][1]

    line_starts = _line_starts(text)
    weak_line_start = _char_to_line(line_starts, weak_char_start)
    weak_line_end = _char_to_line(line_starts, max(0, weak_char_end - 1))
    ctx_line_start = max(1, weak_line_start - max(0, neighborhood_lines))
    ctx_line_end = weak_line_end + max(0, neighborhood_lines)

    lines = text.splitlines()
    # 1-based line numbers to Python slice bounds.
    excerpt = "\n".join(lines[max(0, ctx_line_start - 1) : min(len(lines), ctx_line_end)])

    tactics = split_tactic_segments(text)
    tactic_start = None
    tactic_end = None
    if tactics:
        overlap_indices = [
            idx
            for idx, (seg_start, seg_end) in enumerate(tactics)
            if not (seg_end <= weak_char_start or seg_start >= weak_char_end)
        ]
        if overlap_indices:
            tactic_start = min(overlap_indices)
            tactic_end = max(overlap_indices)

    return {
        "weakest_window_start_token": weak_tok_start,
        "weakest_window_end_token": weak_tok_end,
        "weakest_window_start_line": weak_line_start,
        "weakest_window_end_line": weak_line_end,
        "weakest_context_start_line": ctx_line_start,
        "weakest_context_end_line": ctx_line_end,
        "weakest_excerpt": excerpt,
        "tactic_segmentation_used": bool(tactics),
        "weakest_tactic_index_start": tactic_start,
        "weakest_tactic_index_end": tactic_end,
    }
