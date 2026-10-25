"""OSNet preentrenat amb càrrega local verificada i preprocessament compatible amb l'estudi 05.

No descarrega pesos ni consulta deteccions de pose. El model s'instancia
només al primer cache miss; validar el perfil no executa xarxes neuronals.
"""

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path

from trampoline_vision.contracts.appearance import CandidateEmbedding, FrameAppearance
from trampoline_vision.tracking.errors import TrackingError


def file_sha256(path: Path) -> str:
    """Identifica bytes sense carregar vídeos o checkpoints sencers en memòria."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class OSNetExtractor:
    """Descriptor OSNet x0.25 MSMT17 de 512 components, independent del tracker."""

    def __init__(self, config):
        """Valida pesos i versions abans d'obrir el vídeo o publicar resultats."""
        self.config, self.model = config, None
        path = Path(config.weights)
        try:
            if not path.is_file() or file_sha256(path) != config.sha256:
                raise TrackingError("Missing or mismatched ReID weights; prepare the configured local model")
            self.versions = {name: version(name) for name in ("boxmot", "torch", "torchvision", "numpy", "opencv-python", "av")}
        except (OSError, PackageNotFoundError) as exc:
            raise TrackingError("Appearance requires local weights and trampoline-vision[tracking-reid]") from exc
        if self.versions["boxmot"] != "16.0.9" or path.name != "osnet_x0_25_msmt17.pt":
            raise TrackingError("This provider supports BoxMOT 16.0.9 osnet_x0_25_msmt17.pt")
        identity = {"provider": "osnet_x0_25_msmt17", "weights_sha256": config.sha256,
                    "preprocessing": "boxmot-16.0.9-bgr-rgb-imagenet-256x128-v1", "dimensions": 512,
                    "device": config.device, "threads": config.threads, "versions": self.versions}
        self.identity = identity
        self.fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def _load(self):
        """Carrega tots els tensors del backbone sense fitxers lock ni descàrrega implícita."""
        import torch
        from boxmot.reid.backbones.osnet import osnet_x0_25
        if self.config.device.startswith("cuda") and not torch.cuda.is_available():
            raise TrackingError("Configured CUDA appearance device is unavailable")
        device = torch.device(self.config.device)
        torch.set_num_threads(self.config.threads)
        model = osnet_x0_25(num_classes=1, pretrained=False, use_gpu=device)
        checkpoint = torch.load(self.config.weights, map_location="cpu", weights_only=True)
        state = checkpoint.get("state_dict", checkpoint)
        state = {key.removeprefix("module."): value for key, value in state.items()}
        target = model.state_dict()
        backbone = {key: value for key, value in target.items() if not key.startswith("classifier.")}
        if any(key not in state or state[key].shape != value.shape for key, value in backbone.items()):
            raise TrackingError("ReID checkpoint does not contain the full OSNet backbone")
        target.update({key: state[key] for key in backbone})
        model.load_state_dict(target, strict=True)
        self.model, self.device = model.to(device).float().eval(), device
        self.backbone_tensors = len(backbone)

    def extract(self, frame, image):
        """Conserva l'ordre de candidats i extreu vectors normalitzats amb el preprocessament fixat."""
        import cv2
        import numpy as np
        import torch
        candidates = [c for c in frame.candidates if c.measurement is not None]
        if not candidates:
            return FrameAppearance(frame.source.context, self.fingerprint, ())
        if image is None or image.shape != (frame.source.context.height_px, frame.source.context.width_px, 3):
            raise TrackingError("ReID requires the matching original BGR frame")
        if self.model is None:
            self._load()
        crops = torch.empty((len(candidates), 3, 256, 128), dtype=torch.float32, device=self.device)
        for index, candidate in enumerate(candidates):
            box = candidate.measurement.bbox
            x0, y0, x1, y1 = np.asarray([box.x_min, box.y_min, box.x_max, box.y_max], dtype=np.float32).round().astype(int)
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(image.shape[1], x1), min(image.shape[0], y1)
            if x1 <= x0 or y1 <= y0:
                raise TrackingError("Candidate has no visible crop for appearance extraction")
            crop = cv2.cvtColor(cv2.resize(image[y0:y1, x0:x1], (128, 256), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
            crops[index] = torch.from_numpy(crop).to(self.device, dtype=torch.float32).permute(2, 0, 1)
        mean = torch.tensor([.485, .456, .406], device=self.device).view(1, 3, 1, 1)
        std = torch.tensor([.229, .224, .225], device=self.device).view(1, 3, 1, 1)
        with torch.inference_mode():
            features = self.model((crops / 255 - mean) / std).cpu().numpy()
        features = features / np.linalg.norm(features, axis=1, keepdims=True)
        if features.shape != (len(candidates), 512) or not np.isfinite(features).all():
            raise TrackingError("Invalid OSNet descriptors")
        return FrameAppearance(frame.source.context, self.fingerprint, tuple(
            CandidateEmbedding(c.candidate_id, tuple(float(value) for value in vector))
            for c, vector in zip(candidates, features)))

    def describe(self):
        """Retorna procedència i indica si aquesta execució ha necessitat carregar el model."""
        return {**self.identity, "fingerprint": self.fingerprint, "weights_path": self.config.weights,
                "model_loaded": self.model is not None, "verified_backbone_tensors": getattr(self, "backbone_tensors", None)}
