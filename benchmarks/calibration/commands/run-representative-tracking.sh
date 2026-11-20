#!/usr/bin/env bash
# Replay acotat a 12 clips. La inferència només s'executa si falta el CSV verificat.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
dataset=${CALIBRATION_DATASET:-"$repo/data/calibration-v1"}
results=${CALIBRATION_RESULTS:-"$repo/runs/calibration"}
image=${CALIBRATION_IMAGE:-trampoline-vision:calibration-gpu-v1}
threads=${CALIBRATION_CPUS:-8}
gpu=${CALIBRATION_GPU:-0}
test -f "$dataset/corpus.json" || { echo "Falta el corpus al paquet $dataset" >&2; exit 1; }
docker image inspect "$image" >/dev/null || { echo "Falta la imatge de calibratge $image" >&2; exit 1; }
mkdir -p -- "$results"
extra=()
if [[ -n "${CALIBRATION_EXTRA_REFERENCES:-}" ]]; then
  test -d "$CALIBRATION_EXTRA_REFERENCES"
  extra+=(--mount "type=bind,src=$CALIBRATION_EXTRA_REFERENCES,dst=/extra-references,readonly")
fi
exec docker run --rm --init --network none --gpus "device=$gpu" --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus "$threads" --shm-size 1g \
  -e PYTHONPATH=/workspace/src:/workspace -w /workspace \
  --mount "type=bind,src=$repo,dst=/workspace,readonly" \
  --mount "type=bind,src=$dataset,dst=/data,readonly" \
  --mount "type=bind,src=$results,dst=/results" \
  "${extra[@]}" "$image" -m benchmarks.calibration.tools.representative_tracking \
  --dataset /data --results /results --device cuda:0 --threads "$threads" "$@"
