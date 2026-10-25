#!/usr/bin/env bash
# Executar amb bash; no requereix canviar els permisos del checkout de Windows.
set -euo pipefail
task_repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
task_dataset=${CALIBRATION_DATASET:-"$task_repo_root/data/calibration-v1"}
task_results=${CALIBRATION_RESULTS:-"$task_repo_root/runs/calibration"}
task_image=${CALIBRATION_IMAGE:-trampoline-vision:calibration-gpu-v1}
task_cpus=${CALIBRATION_CPUS:-8}
task_gpu=${CALIBRATION_GPU:-0}
task_extra_mounts=()
task_extra_args=()
if [[ -n "${CALIBRATION_ANNOTATIONS:-}" ]]; then
  test -d "$CALIBRATION_ANNOTATIONS" || { echo "No existeix CALIBRATION_ANNOTATIONS" >&2; exit 1; }
  task_extra_mounts+=(--mount "type=bind,src=$CALIBRATION_ANNOTATIONS,dst=/annotations,readonly")
  task_extra_args+=(--annotations /annotations)
fi
test -f "$task_dataset/corpus.json" || { echo "Falta el paquet de dades: $task_dataset" >&2; exit 1; }
mkdir -p -- "$task_results"
docker build --target gpu -f "$task_repo_root/benchmarks/calibration/Dockerfile" \
  --build-arg "TORCH_INDEX_URL=${CALIBRATION_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}" \
  -t "$task_image" "$task_repo_root"
exec docker run --rm --init --network none --gpus "device=$task_gpu" \
  --user "$(id -u):$(id -g)" --cpus "$task_cpus" --shm-size 1g \
  --mount "type=bind,src=$task_dataset,dst=/data,readonly" \
  --mount "type=bind,src=$task_results,dst=/results" \
  "${task_extra_mounts[@]}" \
  "$task_image" --dataset /data --output /results/screen-v1 --device cuda:0 --threads "$task_cpus" "${task_extra_args[@]}" "$@"
