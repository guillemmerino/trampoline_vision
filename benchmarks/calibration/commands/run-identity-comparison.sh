#!/usr/bin/env bash
# Compara identitats amb CSV obligatoris; per defecte només comprova el protocol.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
dataset=${CALIBRATION_DATASET:-"$repo/data/calibration-v1"}
results=${CALIBRATION_RESULTS:-"$repo/runs/calibration"}
image=${CALIBRATION_IMAGE:-trampoline-vision:calibration-gpu-v1}
test -d "$results"
docker image inspect "$image" >/dev/null
image_id=$(docker image inspect --format '{{.Id}}' "$image")
exec docker run --rm --init --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 4 --memory 8g --shm-size 1g \
  -e PYTHONPATH=/workspace/src:/workspace -e PYTHONDONTWRITEBYTECODE=1 \
  -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 -e CALIBRATION_IMAGE_ID="$image_id" \
  -w /workspace \
  --mount "type=bind,src=$repo,dst=/workspace,readonly" \
  --mount "type=bind,src=$dataset,dst=/data,readonly" \
  --mount "type=bind,src=$results,dst=/results" \
  "$image" -m benchmarks.calibration.tools.identity_comparison "$@"
