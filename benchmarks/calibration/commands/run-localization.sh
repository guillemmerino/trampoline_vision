#!/usr/bin/env bash
# Candidat principal 0,001 i control 0,002; sense ampliar casos ni executar trackers.
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
export CALIBRATION_RUNNER=iteration
export CALIBRATION_ANNOTATIONS=${CALIBRATION_ANNOTATIONS:-"$task_root/benchmarks/calibration/annotations/pilot-v1/references"}
exec bash "$task_root/benchmarks/calibration/commands/run-server.sh" \
  --plan benchmarks/calibration/config/iterations/03-localization-candidates.json \
  --output /results/localization-candidates-v1 "$@"
