#!/usr/bin/env bash
# Round 3: Flash-Next with parallel requests on the 120-case evaluation set.
# Runs every stage, writes docs/history/<date>-round3-flash-next.md, and
# commits and pushes that report. Stages continue if one fails.
#
# Usage: scripts/run_round3.sh [RESULTS_DIR]   (default data/vlm_eval/r3)
set -u
cd "$(dirname "$0")/.."
R=${1:-data/vlm_eval/r3}
M=data/eval_set/manifest.jsonl
mkdir -p "$R"
LOG="$R/workflow.log"
run() {  # run NAME ARGS...
    local name=$1; shift
    echo "$(date -Is) start $name" >> "$LOG"
    uv run python scripts/run_vlm_eval.py --manifest "$M" --models flash-next \
        --out "$R/$name" "$@" > "$R/$name.log" 2>&1
    echo "$(date -Is) end $name rc=$?" >> "$LOG"
}

[ -f "$M" ] || uv run python scripts/build_eval_set.py >> "$LOG" 2>&1

# 1. Throughput and stability: same task at 1..16 parallel requests.
for w in 1 2 4 8 16; do
    run "s1_chat_w$w" --modes chat --views pair --workers "$w"
done
run s1_jev_w1 --modes jev --views pair --workers 1
run s1_jev_w8 --modes jev --views pair --workers 8
# 2. Without a reference solution (assignment text), and text + reference.
run s2_views --modes chat --views task,task_pair --workers 8
# 3. Reasoning on.
run s3_thinking --modes chat --views pair --workers 8 --thinking
# 4. Smaller images.
run s4_scale075 --modes chat --views pair --workers 8 --scale 0.75
run s4_scale050 --modes chat --views pair --workers 8 --scale 0.5
# 5. JEV with the overall question only.
run s5_jev_overall --modes jev --views pair --workers 8 --jev-overall-only

# Report, commit, push.
REPORT="docs/history/$(date +%Y-%m-%d)-round3-flash-next.md"
uv run python scripts/report_round3.py "$R" "$REPORT" >> "$LOG" 2>&1
git add "$REPORT" && git commit -q -m "Round-3 report: Flash-Next with parallel requests" \
    && git push -q origin main >> "$LOG" 2>&1
echo "$(date -Is) done report=$REPORT" >> "$LOG"
