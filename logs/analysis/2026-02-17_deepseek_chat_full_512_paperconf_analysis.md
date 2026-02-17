# Corrected Confidence Analysis: 2026-02-17_155535Z_deepseek_chat_full_512_prescreen_0to1_paperconf

## Configuration
- Token confidence method: `paper_topk`
- Token confidence top-k: 20
- Token confidence require full top-k: False
- Token confidence fallback to chosen: False

## Integrity
- Joined rows: 8192
- samples_only: 0
- metrics_only: 0
- verdicts_only: 0

## Baseline
- Attempt pass rate: 0.366577 (3003/8192)
- Theorem solved rate: 1.000000

## Global Correlation
- avg_logprob: point_biserial=-0.490952, AUC=0.169098
- lowest_group_confidence: point_biserial=-0.448371, AUC=0.235759
- bottom10_group_confidence: point_biserial=-0.452038, AUC=0.238292
- tail_confidence: point_biserial=-0.490991, AUC=0.169573

## Filtering (Top-k% by confidence within theorem)
- lowest_group_confidence:
  - baseline attempt/theorem: 0.366577 / 1.000000
  - top 10%: attempts=832, attempt_success=0.213942, theorem_solved=0.437500
  - top 25%: attempts=2048, attempt_success=0.287598, theorem_solved=0.437500
  - top 50%: attempts=4096, attempt_success=0.321045, theorem_solved=0.500000
- bottom10_group_confidence:
  - baseline attempt/theorem: 0.366577 / 1.000000
  - top 10%: attempts=832, attempt_success=0.205529, theorem_solved=0.437500
  - top 25%: attempts=2048, attempt_success=0.290039, theorem_solved=0.437500
  - top 50%: attempts=4096, attempt_success=0.322021, theorem_solved=0.500000
- tail_confidence:
  - baseline attempt/theorem: 0.366577 / 1.000000
  - top 10%: attempts=832, attempt_success=0.093750, theorem_solved=0.312500
  - top 25%: attempts=2048, attempt_success=0.169434, theorem_solved=0.312500
  - top 50%: attempts=4096, attempt_success=0.259277, theorem_solved=0.500000

## Theorem Pass Rates
- amc12a_2021_p7: 21/512 (0.041016), unique_texts=60
- mathd_algebra_455: 24/512 (0.046875), unique_texts=8
- mathd_numbertheory_84: 24/512 (0.046875), unique_texts=8
- mathd_numbertheory_961: 43/512 (0.083984), unique_texts=9
- mathd_algebra_393: 56/512 (0.109375), unique_texts=111
- mathd_algebra_536: 66/512 (0.128906), unique_texts=90
- mathd_numbertheory_188: 111/512 (0.216797), unique_texts=46
- mathd_numbertheory_739: 125/512 (0.244141), unique_texts=6
- aime_1996_p5: 130/512 (0.253906), unique_texts=451
- algebra_apb4leq8ta4pb4: 153/512 (0.298828), unique_texts=140
- algebra_binomnegdiscrineq_10alt28asqp1: 205/512 (0.400391), unique_texts=8
- algebra_sqineq_36azm9asqle36zsq: 308/512 (0.601562), unique_texts=16
- amc12a_2009_p2: 369/512 (0.720703), unique_texts=23
- mathd_numbertheory_132: 412/512 (0.804688), unique_texts=23
- mathd_numbertheory_200: 474/512 (0.925781), unique_texts=12
- mathd_numbertheory_102: 482/512 (0.941406), unique_texts=4

## Mixed Same-Text Outcomes
- Mixed keys count: 11
- aime_1996_p5: 4/8 pass, fail_error_classes={'unsolved_goals': 4}
- aime_1996_p5: 1/4 pass, fail_error_classes={'unsolved_goals': 3}
- aime_1996_p5: 1/5 pass, fail_error_classes={'unsolved_goals': 4}
- aime_1996_p5: 3/11 pass, fail_error_classes={'unsolved_goals': 7, 'tactic_failure': 1}
- aime_1996_p5: 1/5 pass, fail_error_classes={'unsolved_goals': 3, 'tactic_failure': 1}
- aime_1996_p5: 3/10 pass, fail_error_classes={'unsolved_goals': 6, 'tactic_failure': 1}
- aime_1996_p5: 1/2 pass, fail_error_classes={'unsolved_goals': 1}
- aime_1996_p5: 1/4 pass, fail_error_classes={'unsolved_goals': 2, 'tactic_failure': 1}
- aime_1996_p5: 1/3 pass, fail_error_classes={'unsolved_goals': 2}
- aime_1996_p5: 1/3 pass, fail_error_classes={'unsolved_goals': 2}
