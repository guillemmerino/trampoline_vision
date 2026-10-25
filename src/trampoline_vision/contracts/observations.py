"""Contractes que comparteixen la ingestió i els futurs dominis d'anàlisi.

Un lector converteix dades externes a aquests objectes abans que entrin al
pipeline. Les coordenades són píxels del vídeo original; els temps són
segons relatius al primer fotograma. No hi ha inferència ni tracking aquí.

Les dataclasses frozen impedeixen reassignar camps després de construir
l'objecte. Les tuples preserven l'ordre de fotogrames i articulacions.
__post_init__ comprova les invariants explícites: els tipus anotats,
per si sols, no validen els valors durant l'execució.
"""

from dataclasses import dataclass
import math
from pathlib import Path

from trampoline_vision.contracts.geometry import BoundingBox


# L’ordre és el d’OpenPose BODY_25. Els noms fan explícita la semàntica
# dels índexs i permeten detectar vectors incomplets o reordenats.
BODY25_NAMES = (
    "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
    "left_shoulder", "left_elbow", "left_wrist", "mid_hip", "right_hip",
    "right_knee", "right_ankle", "left_hip", "left_knee", "left_ankle",
    "right_eye", "left_eye", "right_ear", "left_ear", "left_big_toe",
    "left_small_toe", "left_heel", "right_big_toe", "right_small_toe", "right_heel",
)
# Versió escrita a les exportacions; no activa cap migració automàtica.
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class FrameContext:
    """Situa un fotograma dins del vídeo i del seu sistema de coordenades.

    Agrupa identificador, índex intern zero-based, temps de presentació,
    durada i dimensions. És el context de totes les deteccions d'aquell
    instant i existeix també quan no hi ha cap persona detectada.
    """
    video_id: str  # ID del vídeo/cas al qual pertany aquest instant.
    frame_index: int  # Índex intern començant a 0, independent del nom JSON extern.
    timestamp_s: float  # Inici de presentació del fotograma, en segons des de l’inici intern.
    duration_s: float  # Durada d’aquest fotograma; no és la durada d’un salt.
    width_px: int  # Amplada de la imatge original que referencia les coordenades.
    height_px: int  # Alçada de la imatge original, amb Y creixent cap avall.

    def __post_init__(self) -> None:
        """Rebutja índexs, temps o dimensions que impedirien situar observacions.

        S'executa automàticament després del constructor generat per dataclass.
        Un fotograma pot començar a 0 s, però ha de tenir durada positiva.
        """
        if not self.video_id or type(self.frame_index) is not int or self.frame_index < 0:
            raise ValueError("A frame needs a video ID and a non-negative integer index")
        if not math.isfinite(self.timestamp_s) or self.timestamp_s < 0:
            raise ValueError("Frame timestamp must be finite and non-negative")
        if not math.isfinite(self.duration_s) or self.duration_s <= 0:
            raise ValueError("Frame duration must be finite and positive")
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("Frame dimensions must be positive")


@dataclass(frozen=True)
class VideoAsset:
    """Descriu el vídeo i conserva la seva línia temporal completa.

    No conté les imatges. timestamps_s i frame_durations_s tenen una entrada
    per fotograma; són la referència temporal encara que els FPS variïn.
    source_start_s conserva l'origen extern que s'ha restat per començar a 0.
    warnings registra aproximacions, com estimar la durada del darrer fotograma.
    """
    video_id: str  # Identificador estable del cas durant aquesta anàlisi.
    path: Path  # Ruta del vídeo original; no és un buffer amb totes les imatges.
    width_px: int  # Dimensions comunes als fotogrames d’aquest vídeo.
    height_px: int  # Es rebutgen canvis de dimensions durant el sondeig.
    fps: float | None  # Freqüència mitjana informada; els timestamps governen el temps real.
    timestamps_s: tuple[float, ...]  # Una marca de presentació per fotograma, normalitzada a inici 0.
    frame_durations_s: tuple[float, ...]  # Una durada per fotograma; la darrera pot tenir un avís d’estimació.
    source_start_s: float = 0.0  # Origen temporal extern restat durant la normalització.
    warnings: tuple[str, ...] = ()  # Avisos del sondeig que s’han de conservar a l’informe.

    def __post_init__(self) -> None:
        """Comprova coherència de la línia temporal i validesa de cada context.

        Exigeix vídeo no buit, tantes durades com temps, inici intern a zero i
        temps estrictament creixents. Crear cada context reutilitza les seves
        validacions sense duplicar-les aquí.
        """
        if not self.timestamps_s or len(self.timestamps_s) != len(self.frame_durations_s):
            raise ValueError("Video needs one timestamp and duration per frame")
        if self.timestamps_s[0] != 0.0:
            raise ValueError("Internal video time must start at zero")
        if self.fps is not None and (not math.isfinite(self.fps) or self.fps <= 0):
            raise ValueError("Invalid reported frame rate")
        if not math.isfinite(self.source_start_s):
            raise ValueError("Invalid source time origin")
        for index in range(self.frame_count):
            self.frame(index)
            if index and self.timestamps_s[index] <= self.timestamps_s[index - 1]:
                raise ValueError("Presentation timestamps must increase strictly")

    @property
    def frame_count(self) -> int:
        """Retorna el nombre de fotogrames amb temps llegit, a partir de la línia temporal."""
        return len(self.timestamps_s)

    @property
    def duration_s(self) -> float:
        """Calcula el final del vídeo: inici de l'últim fotograma més la seva durada.

        El temps de l'últim fotograma indica quan comença, no quan acaba el clip.
        """
        return self.timestamps_s[-1] + self.frame_durations_s[-1]

    def frame(self, index: int) -> FrameContext:
        """Construeix el context del fotograma intern index, sense llegir-ne la imatge.

        Retorna un FrameContext amb temps i dimensions del vídeo. Genera
        IndexError si l'índex queda fora de la línia temporal disponible.
        """
        if not 0 <= index < self.frame_count:
            raise IndexError(index)
        return FrameContext(self.video_id, index, self.timestamps_s[index],
                            self.frame_durations_s[index], self.width_px, self.height_px)


@dataclass(frozen=True)
class KeypointObservation:
    """Una articulació observada, amb ubicació, confiança i validesa separades.

    x/y són píxels originals o None si no s'utilitza el punt. confidence és
    la confiança del backend, sense interpretar-la com una probabilitat
    d'encert. valid no garanteix precisió: el lector actual l'activa quan
    OpenPose dona confiança positiva. in_frame indica si cau dins la imatge;
    un punt observat fora de la imatge es conserva i es marca com a tal.
    """
    name: str  # Nom anatòmic segons l’esquema declarat, no un índex sense significat.
    x: float | None  # Píxels des de l’esquerra; None si el punt no s’utilitza.
    y: float | None  # Píxels des de dalt; None si el punt no s’utilitza.
    confidence: float  # Valor del model entre 0 i 1; no és una nota ni una probabilitat calibrada.
    valid: bool  # Observació utilitzable segons la política d’entrada; no implica precisió alta.
    in_frame: bool | None  # True/False per a punts observats; None si no hi ha coordenades.

    def __post_init__(self) -> None:
        """Valida rang de confiança i coherència entre validesa i coordenades.

        Un punt vàlid necessita X/Y finits i un indicador de límits explícit.
        Un punt absent usa None, no zeros que es podrien confondre amb un marge.
        La comprovació geomètrica d'in_frame la fa el lector, que coneix les dimensions.
        """
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be finite and within [0, 1]")
        if self.valid:
            if self.confidence <= 0 or self.x is None or self.y is None:
                raise ValueError("Valid points require coordinates and positive confidence")
            if not math.isfinite(self.x) or not math.isfinite(self.y):
                raise ValueError("Coordinates must be finite")
            if type(self.in_frame) is not bool:
                raise ValueError("Observed points require an explicit bounds flag")
        elif self.x is not None or self.y is not None or self.in_frame is not None:
            raise ValueError("Missing coordinates and bounds must be null")


@dataclass(frozen=True)
class DetectionProvenance:
    """Permet tornar d'una detecció interna al registre que l'ha originat.

    Conserva fitxer, membre JSON, índex extern de fotograma i posició de la
    persona al JSON. Aquesta posició no és una identitat temporal. variant
    identifica, per exemple, una fusió heretada; rotation_provenance pot ser
    unknown perquè els JSON antics no conserven l'orientació de procedència.
    """
    source_path: str  # ZIP o carpeta que permet recuperar la dada original.
    source_record: str  # Membre JSON dins del ZIP o ruta relativa dins de la carpeta.
    source_frame_index: int  # Número extern abans de convertir-lo a zero-based.
    source_person_index: int  # Posició dins de people; no és la identitat de la persona.
    variant: str  # Tipus de material, per exemple legacy_fused.
    rotation_provenance: str  # Origen d’orientació conegut o unknown si s’ha perdut.


@dataclass(frozen=True)
class PersonDetection:
    """Proposta d'una persona en un únic fotograma, encara sense identitat temporal.

    Reuneix els 25 punts BODY_25, la seva procedència i un detection_id local.
    Actualment el lector genera IDs fotograma:posició. El futur tracker
    haurà d'associar deteccions de diversos instants i crear un track_id.
    skeleton_schema declara la semàntica dels punts; avui només s'admet BODY_25.
    """
    detection_id: str  # ID local al fotograma; context + ID situen l’observació al vídeo.
    keypoints: tuple[KeypointObservation, ...]  # Els 25 punts sempre en el mateix ordre, encara que alguns faltin.
    provenance: DetectionProvenance  # Traça cap al registre extern que ha produït aquest esquelet.
    skeleton_schema: str = "openpose_body25"  # Semàntica dels punts; només BODY_25 està implementat ara.

    def __post_init__(self) -> None:
        """Exigeix BODY_25 complet en ordre semàntic, encara que hi hagi punts absents.

        Eliminar una articulació canviaria els índexs de les següents. Conservar
        els 25 noms evita confondre, per exemple, un genoll amb un turmell.
        """
        if self.skeleton_schema != "openpose_body25":
            raise ValueError("Only BODY_25 is implemented in this reader")
        if tuple(point.name for point in self.keypoints) != BODY25_NAMES:
            raise ValueError("BODY_25 needs exactly 25 points in declared semantic order")


@dataclass(frozen=True)
class PersonBoxDetection:
    """Persona detectada per caixa, sense obligar a disposar d'una pose.

    detection_id és local al fotograma. El tracker crea les identitats
    temporals; un futur matching hi associarà observacions articulars.
    """

    detection_id: str  # Referència local, independent del tracker i del detector concret.
    bbox: BoundingBox  # Caixa observada en coordenades originals.
    score: float  # Confiança original, sense reinterpretar-la com a qualitat de tracking.
    provenance: DetectionProvenance  # Fitxer, fila i índex extern que permeten auditar-la.
    class_id: int = 0  # Aquesta font només admet deteccions de persona.

    def __post_init__(self) -> None:
        """Valida identitat local, geometria, confiança i procedència sense fabricar punts."""
        if not isinstance(self.detection_id, str) or not self.detection_id.strip():
            raise ValueError("Box detection requires a local ID")
        if not isinstance(self.bbox, BoundingBox) or not isinstance(self.provenance, DetectionProvenance):
            raise ValueError("Box detection requires geometry and provenance")
        if type(self.score) not in (int, float) or not math.isfinite(self.score) or not 0 <= self.score <= 1:
            raise ValueError("Box detection score must be in [0, 1]")
        if type(self.class_id) is not int or self.class_id != 0:
            raise ValueError("Only person class 0 is supported")

    @property
    def keypoints(self) -> tuple:
        """Exposa absència real de pose: cap punt ni coordenada artificial."""
        return ()

    @property
    def skeleton_schema(self) -> None:
        """Indica que aquesta observació de caixa no conté un esquelet."""
        return None


@dataclass(frozen=True)
class FrameDetections:
    """Unitat del pipeline: un context temporal i totes les deteccions d'aquell instant.

    source_status=present amb deteccions buides vol dir que el JSON no
    conté persones. missing vol dir que no hi ha registre d'origen per al
    fotograma. Ambdues situacions mantenen el temps, però tenen causes diferents.
    """
    context: FrameContext  # Temps i geometria comuns a les deteccions del fotograma.
    detections: tuple[PersonDetection | PersonBoxDetection, ...]  # Zero o més propostes de persona, encara sense tracking.
    source_status: str  # present: hi ha registre; missing: manca el registre d’origen.

    def __post_init__(self) -> None:
        """Valida l'estat de la font i impedeix IDs repetits dins d'un fotograma.

        Un registre absent no pot afirmar que contingui observacions. La
        unicitat aquí és local al fotograma; no s'exigeix continuïtat temporal.
        """
        if self.source_status not in {"present", "missing"}:
            raise ValueError("Unknown frame source status")
        if self.source_status == "missing" and self.detections:
            raise ValueError("A missing source record cannot contain observations")
        ids = [d.detection_id for d in self.detections]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate detection IDs in a frame")
