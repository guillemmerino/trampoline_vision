# Proves

Proves unitàries i d'integració de contractes d'entrada, manifests, temps, lectura OpenPose i CLI.

```text
python -B -m unittest discover -s tests -v
docker compose --profile test run --rm tests
```

La prova real FFmpeg s'omet localment si no hi ha eines al PATH i s'executa a la imatge de tests.
Vegeu [validació](../docs/12-validation-strategy.md).
