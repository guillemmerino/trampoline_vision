#!/usr/bin/env bash
# 18 vídeos complets, 0,001 principal i 0,002 control, cap tracker.
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
export CALIBRATION_RUNNER=iteration
export CALIBRATION_ANNOTATIONS=${CALIBRATION_ANNOTATIONS:-"$task_root/benchmarks/calibration/annotations/expanded-v1/references"}
exec bash "$task_root/benchmarks/calibration/commands/run-server.sh" \
  --plan benchmarks/calibration/archive/detection-preparation-v1/config/iterations/04-expanded-localization.json \
  --output /results/expanded-localization-v1 "$@"
