# Construcció GPU portable. Les dades i els pesos sempre es munten en lectura.
ARG VALIDATION_BASE=trampoline-vision:recovery-fragments-check
FROM python:3.11-slim-bookworm AS gpu
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    YOLO_AUTOINSTALL=false YOLO_OFFLINE=true YOLO_CONFIG_DIR=/tmp/ultralytics MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/trampoline-vision
COPY pyproject.toml README.md ./
# Les dependències queden al cache quan canvien codi o plans d'iteració.
RUN python -m pip install --no-cache-dir --index-url ${TORCH_INDEX_URL} torch==2.7.1 torchvision==0.22.1 \
    && python -c 'import tomllib; p=tomllib.load(open("pyproject.toml","rb"))["project"]["optional-dependencies"]; open("/tmp/calibration-requirements.txt","w").write("\n".join(r for k in ("tracking","tracking-reid-cuda128","visualization") for r in p[k]))' \
    && python -m pip install --no-cache-dir -r /tmp/calibration-requirements.txt ultralytics==8.3.116 psutil==7.0.0 ultralytics-thop==2.0.18
COPY src/ ./src/
COPY configs/ ./configs/
COPY benchmarks/calibration/ ./benchmarks/calibration/
RUN python -m pip install --no-cache-dir --no-deps . \
    && python -m pip check \
    && python -m pip freeze > /opt/calibration-environment.txt
ENTRYPOINT ["python", "-m", "benchmarks.calibration", "run"]
CMD ["--dataset", "/data", "--output", "/results/screen-v1"]

# Verificació local en CPU sobre el runtime ja comprovat del projecte. No és
# una imatge de desplegament; permet validar sense descarregar una altra wheel CUDA.
FROM ${VALIDATION_BASE} AS validation
USER root
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    YOLO_AUTOINSTALL=false YOLO_OFFLINE=true YOLO_CONFIG_DIR=/tmp/ultralytics MPLCONFIGDIR=/tmp/matplotlib HOME=/tmp
WORKDIR /opt/trampoline-vision
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY benchmarks/calibration/ ./benchmarks/calibration/
COPY tests/ ./tests/
RUN python -m pip install --no-cache-dir --no-deps . ultralytics==8.3.116 psutil==7.0.0 ultralytics-thop==2.0.18
ENTRYPOINT ["python", "-B", "-m", "unittest"]
CMD ["discover", "-s", "tests", "-v"]
