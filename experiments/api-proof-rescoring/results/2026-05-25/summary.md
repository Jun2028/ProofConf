# Prompt-Logprob Proof-Body Scoring

- Unique theorems: `122`
- Attempt rows analyzed: `35749`
- Attempt rows scored: `35749`
- Correct attempts: `222`
- Wrong attempts: `35527`
- Scoring errors: `0`
- Missing metrics: `0`

## Configuration
- Endpoint: `/v1/completions`
- Model: `Goedel-Prover-V2-8B`
- Tokenizer: `SOURCE_ARTIFACTS/models/Goedel-LM__Goedel-Prover-V2-8B`
- Offset source: `tokenizer`
- Request: `echo=true`, `max_tokens=0`, `logprobs=0`, `prompt_logprobs=0`
- Body mask: `tokenizer` token offsets with `add_special_tokens=false`
- Window: `size=24`, `stride=6`
- Tail tokens: `256`

## Baseline Labels
- Attempt pass rate: `0.006210`
- Theorem solved rate: `0.893443`

## Global Correlation
- `avg_logprob`: point_biserial=`-0.048884`, AUC=`0.341240`
- `min_logprob`: point_biserial=`0.058387`, AUC=`0.705206`
- `bottom10_logprob`: point_biserial=`-0.048111`, AUC=`0.342360`
- `lowest_window_logprob`: point_biserial=`0.046435`, AUC=`0.661939`
- `tail_logprob`: point_biserial=`-0.049842`, AUC=`0.334296`

## Within-Theorem AUC
- `avg_logprob`: mean_per_theorem_auc=`0.508107`, below_0.5=`29/63`
- `min_logprob`: mean_per_theorem_auc=`0.517396`, below_0.5=`26/63`
- `bottom10_logprob`: mean_per_theorem_auc=`0.460125`, below_0.5=`31/63`
- `lowest_window_logprob`: mean_per_theorem_auc=`0.527688`, below_0.5=`32/63`
- `tail_logprob`: mean_per_theorem_auc=`0.499780`, below_0.5=`31/63`

## Filtering (Top-k% by score within theorem)
- `avg_logprob`:
  - baseline attempt/theorem: `0.006210` / `0.893443`
  - top 10%: attempts=`3645`, attempt_success=`0.020302`, theorem_solved=`0.590164`
  - top 25%: attempts=`8985`, attempt_success=`0.009794`, theorem_solved=`0.647541`
  - top 50%: attempts=`17897`, attempt_success=`0.006705`, theorem_solved=`0.786885`
- `min_logprob`:
  - baseline attempt/theorem: `0.006210` / `0.893443`
  - top 10%: attempts=`3645`, attempt_success=`0.019479`, theorem_solved=`0.565574`
  - top 25%: attempts=`8985`, attempt_success=`0.009683`, theorem_solved=`0.631148`
  - top 50%: attempts=`17897`, attempt_success=`0.006649`, theorem_solved=`0.762295`
- `bottom10_logprob`:
  - baseline attempt/theorem: `0.006210` / `0.893443`
  - top 10%: attempts=`3645`, attempt_success=`0.018381`, theorem_solved=`0.540984`
  - top 25%: attempts=`8985`, attempt_success=`0.009238`, theorem_solved=`0.614754`
  - top 50%: attempts=`17897`, attempt_success=`0.006146`, theorem_solved=`0.754098`
- `lowest_window_logprob`:
  - baseline attempt/theorem: `0.006210` / `0.893443`
  - top 10%: attempts=`3645`, attempt_success=`0.019204`, theorem_solved=`0.573770`
  - top 25%: attempts=`8985`, attempt_success=`0.009905`, theorem_solved=`0.655738`
  - top 50%: attempts=`17897`, attempt_success=`0.006537`, theorem_solved=`0.762295`
- `tail_logprob`:
  - baseline attempt/theorem: `0.006210` / `0.893443`
  - top 10%: attempts=`3645`, attempt_success=`0.019204`, theorem_solved=`0.565574`
  - top 25%: attempts=`8985`, attempt_success=`0.009683`, theorem_solved=`0.639344`
  - top 50%: attempts=`17897`, attempt_success=`0.006593`, theorem_solved=`0.762295`
