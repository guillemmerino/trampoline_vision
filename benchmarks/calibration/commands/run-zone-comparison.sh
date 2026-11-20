#!/usr/bin/env bash
# Compara tres zones amb deteccions verificades ja desades, sense GPU ni tracker.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
dataset=${CALIBRATION_DATASET:-"$repo/data/calibration-v1"}
results=${CALIBRATION_RESULTS:-"$repo/runs/calibration"}
image=${CALIBRATION_IMAGE:-trampoline-vision:calibration-gpu-v1}
threads=${CALIBRATION_CPUS:-8}
test -f "$dataset/corpus.json" || { echo "Falta el corpus a $dataset" >&2; exit 1; }
test -f "$results/expanded-localization-v1/human-review/bundle.json" || { echo "Falta el bundle de deteccions desades" >&2; exit 1; }
test -f "$results/expanded-localization-v1/human-review/review-state.json" || { echo "Falten les decisions humanes" >&2; exit 1; }
docker image inspect "$image" >/dev/null || { echo "Falta la imatge $image" >&2; exit 1; }
exec docker run --rm --init --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus "$threads" --shm-size 1g \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 -w /workspace \
  --mount "type=bind,src=$repo,dst=/workspace,readonly" \
  --mount "type=bind,src=$dataset,dst=/data,readonly" \
  --mount "type=bind,src=$results,dst=/results" \
  "$image" -m benchmarks.calibration.tools.compare_zones \
  --dataset /data --bundle /results/expanded-localization-v1/human-review/bundle.json \
  --decisions /results/expanded-localization-v1/human-review/review-state.json \
  --output /results/zone-comparison-v1 --allow-provisional-references "$@"
