from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_prompt_logprobs as scorer  # noqa: E402


class ScorePromptLogprobsTests(unittest.TestCase):
    def test_split_lean_prefix_body_keeps_context_out_of_body(self) -> None:
        text = """import Mathlib

open Nat

theorem sample (a : Nat) : a = a := by
  rfl
"""

        split = scorer.split_lean_prefix_body(text)

        self.assertTrue(split.prefix.endswith(":= by"))
        self.assertEqual(split.body, "\n  rfl\n")
        self.assertEqual(text[: split.body_start], split.prefix)
        self.assertEqual(text[split.body_start :], split.body)

    def test_body_token_indices_excludes_boundary_crossing_token(self) -> None:
        offsets = [(0, 7), (7, 12), (12, 15), (15, 18), (18, 24)]

        indices, crossing = scorer.body_token_indices(offsets, body_start=14)

        self.assertEqual(indices, [3, 4])
        self.assertEqual(crossing, 1)

    def test_score_response_for_body_uses_only_body_logprobs(self) -> None:
        tokenization = scorer.Tokenization(
            input_ids=[10, 11, 12, 13],
            offsets=[(0, 7), (7, 13), (13, 18), (18, 26)],
        )
        response = {
            "choices": [
                {
                    "logprobs": {
                        "tokens": [
                            "token_id:10",
                            "token_id:11",
                            "token_id:12",
                            "token_id:13",
                        ],
                        "token_logprobs": [None, -9.0, -0.25, -0.75],
                    },
                    "prompt_logprobs": [None, {"11": {"logprob": -9.0}}],
                }
            ]
        }

        metrics = scorer.score_response_for_body(
            response=response,
            tokenization=tokenization,
            body_start=13,
            window_size=2,
            stride=1,
            tail_tokens=1,
            bottom_fraction=0.5,
        )

        self.assertEqual(metrics["body_token_count"], 2)
        self.assertEqual(metrics["scored_token_count"], 2)
        self.assertIs(metrics["prompt_logprobs_present"], True)
        self.assertTrue(math.isclose(metrics["avg_logprob"], -0.5))
        self.assertTrue(math.isclose(metrics["min_logprob"], -0.75))
        self.assertTrue(math.isclose(metrics["tail_logprob"], -0.75))

    def test_aligned_logprobs_accepts_leading_bos_none(self) -> None:
        aligned, shift = scorer.aligned_logprobs_for_tokenization([None, -1.0, -2.0], 2)

        self.assertEqual(aligned, [-1.0, -2.0])
        self.assertEqual(shift, 1)

    def test_response_tokenization_from_echo_uses_text_offsets(self) -> None:
        response = {
            "choices": [
                {
                    "logprobs": {
                        "tokens": ["abc", "de", "f"],
                        "text_offset": [0, 3, 5],
                        "token_logprobs": [-1.0, -2.0, -3.0],
                    }
                }
            ]
        }

        tokenization = scorer.response_tokenization_from_echo(response, "abcdef")

        self.assertEqual(tokenization.offsets, [(0, 3), (3, 5), (5, 6)])


if __name__ == "__main__":
    unittest.main()
