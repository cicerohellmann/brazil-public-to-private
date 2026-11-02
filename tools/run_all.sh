#!/usr/bin/env bash
# Run the source checks end to end: extract -> fetch -> auto_match -> verify.
#   tools/run_all.sh             full run (fetch skips URLs fetched in the last 30 days)
#   tools/run_all.sh --no-fetch  re-run only the tests on the saved snapshots
#   tools/run_all.sh --refresh   re-fetch every source
# Exits with verify.py's code (1 = a verified claim regressed).
#
# Final step, run by hand once every source is final (Cicero approved it as one
# bundled step):  python3 tools/archive_submit.py        (dry run, lists URLs)
#                 python3 tools/archive_submit.py --go   (submits to Save Page Now)
set -euo pipefail
cd "$(dirname "$0")/.."

FETCH=1
FETCH_ARGS=()
for a in "$@"; do
  case "$a" in
    --no-fetch) FETCH=0 ;;
    --refresh) FETCH_ARGS+=(--refresh) ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

python3 tools/extract_claims.py
if [ "$FETCH" = 1 ]; then
  python3 tools/fetch_sources.py ${FETCH_ARGS[@]+"${FETCH_ARGS[@]}"}
fi
python3 tools/auto_match.py
set +e
python3 tools/verify.py
code=$?
set -e
echo "Final step when sources are final: python3 tools/archive_submit.py (dry run; --go to submit)"
exit $code
