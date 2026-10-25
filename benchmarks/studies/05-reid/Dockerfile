# Entorn experimental aïllat: no amplia les dependències del paquet de producció.
# Construir abans el target tracking del projecte; el BASE_IMAGE permet reutilitzar el runtime 0.4.0 verificat.
ARG BASE_IMAGE=trampoline-vision:tracking
FROM ${BASE_IMAGE}
USER root
COPY requirements-frozen.txt /tmp/reid-constraints.txt
# Parella CPU fixada i compatible; evita instal·lar biblioteques CUDA a l'equip local.
RUN python -m pip install --no-cache-dir -c /tmp/reid-constraints.txt torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
RUN python -m pip install --no-cache-dir -c /tmp/reid-constraints.txt boxmot==16.0.9
USER analyst
ENTRYPOINT ["python"]
