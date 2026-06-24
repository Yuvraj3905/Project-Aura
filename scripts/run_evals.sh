#!/usr/bin/env bash
# Regression gate: run every check and fail if any does. This is the eval harness — the
# assertion scripts already encode the quality bars (persona, grounding, no cross-doc bleed,
# spec correctness, follow-up resolution), so a passing run = no regression.
#
#   scripts/run_evals.sh          # everything (incl. the slow LLM storyline ~15-20min)
#   scripts/run_evals.sh --fast   # skip the slow storyline
#
# ponytail: deterministic asserts, not an LLM-judge. Add graded judging only if a real
# regression ever slips past these (none has — they caught the NLU break).
set -uo pipefail
cd "$(dirname "$0")/.."

fast=0; [[ "${1:-}" == "--fast" ]] && fast=1
declare -A result

run() { echo -e "\n=== $1 ==="; bash -c "$2"; result[$1]=$?; }

run "pytest"   "docker compose run --rm --no-deps -v \"\$(pwd)/ml-service/tests:/app/tests\" -v \"\$(pwd)/ml-service/app:/app/app\" --entrypoint pytest ml-service tests/ -q"
run "funnel"   "python3 scripts/funnel_test.py"
run "phase2"   "python3 scripts/phase2_test.py"
run "rewrite"  "python3 scripts/rewrite_test.py"
(( fast )) || run "comparison" "python3 scripts/comparison_test.py"
(( fast )) || run "storyline" "python3 scripts/storyline_test.py"

echo -e "\n===================== EVAL SUMMARY ====================="
fail=0
for name in "${!result[@]}"; do
  if [[ ${result[$name]} -eq 0 ]]; then echo "  PASS  $name"; else echo "  FAIL  $name"; fail=1; fi
done
(( fail )) && { echo "EVALS FAILED"; exit 1; }
echo "ALL EVALS PASSED"
