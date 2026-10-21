#!/usr/bin/env bash
#
# Fetch student submissions from GitLab group for plot grading analysis
#
# Usage:
#   GITLAB_HOST=gitlab.example.org ./tools/fetch_student_submissions.sh <group-path>
#
# Example:
#   GITLAB_HOST=gitlab.example.org \
#       ./tools/fetch_student_submissions.sh my-course/2025/students
#
# Prerequisites:
#   1. Authenticate with your GitLab instance:
#      glab auth login --hostname "$GITLAB_HOST"
#   2. Ensure you have read access to the group that holds the student projects.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: GITLAB_HOST=<host> $0 <group-path>" >&2
    echo "Example: GITLAB_HOST=gitlab.example.org $0 my-course/2025/students" >&2
    exit 2
fi

GITLAB_HOST="${GITLAB_HOST:-gitlab.com}"
GROUP_PATH="$1"
SUBMISSIONS_DIR="./data/student_submissions"
LOG_FILE="./data/fetch_log.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Create output directory
mkdir -p "$SUBMISSIONS_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log "Starting fetch from GitLab group: $GROUP_PATH"

# Check authentication
if ! glab auth status --hostname "$GITLAB_HOST" &>/dev/null; then
    error "Not authenticated to $GITLAB_HOST"
    echo ""
    echo "Please authenticate first:"
    echo "  glab auth login --hostname $GITLAB_HOST"
    exit 1
fi

log "Authentication OK"

# List all projects in the group
log "Fetching project list from group..."

# Get all projects recursively in the group
PROJECT_LIST=$(glab api --hostname "$GITLAB_HOST" \
    "/groups/${GROUP_PATH//\//%2F}/projects?include_subgroups=true&per_page=100" \
    --paginate)

# Parse project information
PROJECT_COUNT=$(echo "$PROJECT_LIST" | jq '. | length')
log "Found $PROJECT_COUNT student projects"

# Create index file
INDEX_FILE="$SUBMISSIONS_DIR/index.json"
echo "$PROJECT_LIST" > "$INDEX_FILE"
log "Project index saved to $INDEX_FILE"

# For each project, clone or update
echo "$PROJECT_LIST" | jq -r '.[] | "\(.id)|\(.path_with_namespace)|\(.ssh_url_to_repo)"' | \
while IFS='|' read -r project_id project_path repo_url; do
    student_name=$(basename "$project_path")
    local_path="$SUBMISSIONS_DIR/$student_name"

    if [ -d "$local_path/.git" ]; then
        log "Updating: $student_name"
        (cd "$local_path" && git pull --quiet) || warn "Failed to update $student_name"
    else
        log "Cloning: $student_name"
        git clone --quiet "$repo_url" "$local_path" || error "Failed to clone $student_name"
    fi
done

log "Fetch complete! Submissions stored in: $SUBMISSIONS_DIR"

# Generate summary
TOTAL_REPOS=$(find "$SUBMISSIONS_DIR" -maxdepth 1 -type d -name "*" | wc -l)
log "Total repositories: $((TOTAL_REPOS - 1))"  # -1 for submissions dir itself

# Find all Python files with plotting assignments
log "Scanning for plotting assignments..."

find "$SUBMISSIONS_DIR" -name "*.py" -type f | \
    grep -E "(plot_docstr|simple_taylor|kerrzelle|einfache_animation)" | \
    sort > "$SUBMISSIONS_DIR/plotting_files.txt"

PLOT_FILE_COUNT=$(wc -l < "$SUBMISSIONS_DIR/plotting_files.txt")
log "Found $PLOT_FILE_COUNT plotting assignment files"

echo ""
echo "Summary:"
echo "  Student repositories: $((TOTAL_REPOS - 1))"
echo "  Plotting files found: $PLOT_FILE_COUNT"
echo "  Data location: $SUBMISSIONS_DIR"
echo "  File list: $SUBMISSIONS_DIR/plotting_files.txt"
