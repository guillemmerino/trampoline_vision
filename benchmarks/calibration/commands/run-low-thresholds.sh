#!/usr/bin/env bash
# Segona prova: només detector; no altera el pla per defecte de run-iteration.sh.
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
export CALIBRATION_RUNNER=iteration
export CALIBRATION_ANNOTATIONS=${CALIBRATION_ANNOTATIONS:-"$task_root/benchmarks/calibration/annotations/pilot-v1/references"}
exec bash "$task_root/benchmarks/calibration/commands/run-server.sh" \
  --plan benchmarks/calibration/config/iterations/02-low-detector-thresholds.json \
  --output /results/low-detector-thresholds-v1 "$@"
