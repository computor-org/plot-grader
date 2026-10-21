#!/usr/bin/env bash
# Round 5: the round-4 judge on real 2026 PiP submissions.
# Judge = Flash-Next (chat, pair_tolerant, images at 75 %) PASS and
# tolerant_check() without problems. The strict view `pair` runs once for
# comparison. Tier 1 is in the rows; tolerant_check runs offline in the report.
#
# Prerequisite: data/real2026/manifest.jsonl from
#   scripts/build_real2026.py fetch   (Computor API, read-only)
#   scripts/build_real2026.py build   (official harness labels, renders)
#
# Usage: scripts/run_real2026.sh [RESULTS_DIR]   (default data/vlm_eval/r5)
# Aggregates: scripts/report_real2026.py RESULTS_DIR MANIFEST (prints tables).
set -u
cd "$(dirname "$0")/.."
R=${1:-data/vlm_eval/r5}
M=data/real2026/manifest.jsonl
mkdir -p "$R"
LOG="$R/workflow.log"
run() {  # run NAME ARGS...
    local name=$1; shift
    echo "$(date -Is) start $name" >> "$LOG"
    uv run python scripts/run_vlm_eval.py --manifest "$M" --models flash-next \
        --scale 0.75 --resume --out "$R/$name" "$@" >> "$R/$name.log" 2>&1
    echo "$(date -Is) end $name rc=$?" >> "$LOG"
}

run r5_tolerant --modes chat --views pair_tolerant --workers 1
run r5_strict --modes chat --views pair --workers 1
uv run python scripts/report_real2026.py "$R" "$M" > "$R/aggregates.md" 2>> "$LOG"
echo "$(date -Is) done aggregates=$R/aggregates.md" >> "$LOG"
