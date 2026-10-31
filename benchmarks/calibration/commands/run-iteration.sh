#!/usr/bin/env bash
# Una comanda del host; una iteració explícita; revisió posterior independent.
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
export CALIBRATION_RUNNER=iteration
export CALIBRATION_ANNOTATIONS=${CALIBRATION_ANNOTATIONS:-"$task_root/benchmarks/calibration/annotations/pilot-v1/references"}
exec bash "$task_root/benchmarks/calibration/commands/run-server.sh" --output /results/threshold-robustness-v1 "$@"
