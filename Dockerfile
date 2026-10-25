# Etapa de construcció: genera una wheel del paquet, sense dades ni models.
# El runtime copiarà només l’artefacte instal·lable, no el directori de desenvolupament.
FROM python:3.11-slim-bookworm AS builder
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/
# Construeix el paquet; --no-deps evita construir dependències d’execució (el nucli no en declara).
# Les eines de construcció de pyproject.toml sí que poden descarregar-se.
RUN python -m pip wheel --no-deps --wheel-dir /wheels .

# Entorn CPU d’execució. FFmpeg proporciona ffprobe per consultar temps reals del vídeo.
FROM python:3.11-slim-bookworm AS cpu
# Evita caches Python al disc i buida stdout immediatament, útil amb filesystem només lectura.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# Instal·la eines del vídeo i crea l’usuari que executarà les anàlisis sense root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 analyst
COPY --from=builder /wheels/ /wheels/
# La variant CPU també incorpora l'extra de dibuix/codificació per executar visualize.
# El paquet instal·lat sense extras continua permetent inspect només amb ffprobe.
RUN python -m pip install --no-cache-dir --no-deps /wheels/*.whl \
    && python -m pip install --no-cache-dir 'trampoline-vision[visualization]' \
    && rm -rf /wheels
# La ubicació conserva la relació de germans amb /workspace/TFM usada pel manifest.
WORKDIR /workspace/trampoline-vision
# Només s’inclouen configuracions i manifests; els vídeos es munten externament.
COPY configs/ ./configs/
COPY data/manifests/ ./data/manifests/
# El procés d’anàlisi no necessita privilegis d’administració.
USER analyst
# Compose passa aquí arguments com inspect --config ...; per defecte només mostra ajuda.
ENTRYPOINT ["python", "-m", "trampoline_vision"]
CMD ["--help"]

# Variant de proves amb el mateix runtime CPU, afegint les fixtures i els tests sintètics.
FROM cpu AS test
COPY tests/ /tests/
ENTRYPOINT ["python", "-B", "-m", "unittest"]
CMD ["discover", "-s", "/tests", "-v"]

# Runtime de seguiment; manté l'extra separat de la imatge CPU d'inspecció.
FROM cpu AS tracking
USER root
# La base amb FFmpeg ja proporciona les llibreries de sistema d'OpenCV, inclosa libGL.
RUN python -m pip install --no-cache-dir 'trampoline-vision[tracking]'
USER analyst

# Mateix runtime de seguiment amb proves sintètiques, sense dades del projecte antic.
FROM tracking AS test-tracking
COPY tests/ /tests/
ENTRYPOINT ["python", "-B", "-m", "unittest"]
CMD ["discover", "-s", "/tests", "-v"]

# Variant CPU completa: conserva OC-SORT/ByteTrack i afegeix BoT-SORT/OSNet.
# No incorpora pesos ni executa descàrregues de models en arrencar.
FROM tracking AS tracking-reid
USER root
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch==2.5.1' 'torchvision==0.20.1' \
    && python -m pip install --no-cache-dir 'trampoline-vision[tracking-reid]'
USER analyst

# Comprova tots els adaptadors sense necessitar vídeos ni pesos externs.
FROM tracking-reid AS test-tracking-reid
COPY tests/ /tests/
ENTRYPOINT ["python", "-B", "-m", "unittest"]
CMD ["discover", "-s", "/tests", "-v"]
