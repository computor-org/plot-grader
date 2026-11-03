#!/usr/bin/env bash
# Round 4: strict vs tolerant judging (docs/criteria.md) with Flash-Next on
# the extended evaluation set (round-4 mutations). Writes the report into
# the results directory once data/eval_set/visual_labels.jsonl exists.
#
# Usage: scripts/run_round4.sh [RESULTS_DIR]   (default data/vlm_eval/r4)
set -u
cd "$(dirname "$0")/.."
R=${1:-data/vlm_eval/r4}
M=data/eval_set/manifest.jsonl
L=data/eval_set/visual_labels.jsonl
mkdir -p "$R"
LOG="$R/workflow.log"
run() {  # run NAME ARGS...
    local name=$1; shift
    echo "$(date -Is) start $name" >> "$LOG"
    uv run python scripts/run_vlm_eval.py --manifest "$M" --models flash-next \
        --scale 0.75 --out "$R/$name" "$@" > "$R/$name.log" 2>&1
    echo "$(date -Is) end $name rc=$?" >> "$LOG"
}

run r4_strict --modes chat --views pair --workers 16
run r4_tolerant --modes chat --views pair_tolerant --workers 16
run r4_tolerant_rep --modes chat --views pair_tolerant --workers 16
run r4_jev_tolerant --modes jev --views pair_tolerant --workers 8 --jev-overall-only

if [ -f "$L" ]; then
    REPORT="$R/report.md"
    uv run python scripts/report_round4.py "$R" "$M" "$L" "$REPORT" >> "$LOG" 2>&1
    echo "$(date -Is) done report=$REPORT" >> "$LOG"
else
    echo "$(date -Is) done, no visual labels yet: run report_round4.py by hand" >> "$LOG"
fi
