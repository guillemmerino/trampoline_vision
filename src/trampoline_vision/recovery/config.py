"""Perfils separats de diagnòstic i associació experimental, sense apply."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class FragmentationConfig:
    """Activa preparació offline sense aplicar unions ni carregar models."""

    enabled: bool = True
    policy: str = 'consecutive_observations_v1'

    def __post_init__(self):
        """Rebutja polítiques no implementades i activació amb conversions implícites."""
        if type(self.enabled) is not bool or self.policy != 'consecutive_observations_v1':
            raise ValueError('Expected boolean enabled and consecutive_observations_v1 policy')

    @classmethod
    def from_dict(cls, value):
        """Accepta només esquema 1.0 de fragments, mai esborranys d'associació futura."""
        allowed = {'schema_version', 'task', 'enabled', 'policy'}
        if not isinstance(value, dict) or set(value) - allowed or value.get('schema_version') != '1.0' or value.get('task') != 'inspect_tracking_fragments':
            raise ValueError('Expected schema 1.0 inspect_tracking_fragments with known keys')
        return cls(**{k: v for k, v in value.items() if k not in ('schema_version', 'task')})


@dataclass(frozen=True)
class AssociationParameters:
    """Valors d'experiment, sense probabilitats calibrades ni activació d'apply."""

    max_gap_s: float = 2.
    no_link_cost: float = .55
    appearance_weight: float = .65
    geometry_weight: float = .25
    scale_weight: float = .05
    time_weight: float = .05
    appearance_distance_scale: float = .5
    max_scale_ratio: float = 4.
    distance_base: float = 3.
    distance_growth_per_s: float = 5.
    geometry_growth_per_s: float = 3.
    ambiguity_margin: float = .05
    duplicate_iou: float = .7

    def __post_init__(self):
        """Rebutja booleans, NaN, pesos incoherents i límits que invaliden els costos."""
        for name, value in vars(self).items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f'Invalid association parameter: {name}')
        if self.max_gap_s <= 0 or self.appearance_distance_scale <= 0 or self.max_scale_ratio <= 1:
            raise ValueError('Positive gap/appearance scale and max_scale_ratio > 1 required')
        if not 0 < self.no_link_cost <= 1 or not 0 < self.duplicate_iou <= 1 or self.ambiguity_margin > 1:
            raise ValueError('Invalid no-link, ambiguity or duplicate threshold')
        if not math.isclose(sum(getattr(self, n+'_weight') for n in ('appearance','geometry','scale','time')), 1, abs_tol=1e-9):
            raise ValueError('Association weights must sum to one')


@dataclass(frozen=True)
class RecoveryAuditConfig:
    """Perfil executable explícit, experimental i exclusiu del mode auditoria."""

    profile_id: str
    revision: int = 1
    strategy: str = 'geometry_appearance'
    parameters: AssociationParameters = AssociationParameters()
    mode: str = 'audit'
    status: str = 'experimental'

    def __post_init__(self):
        """No existeix mode apply; un esborrany no es pot activar amb un booleà."""
        if not isinstance(self.profile_id, str) or not self.profile_id.strip() or type(self.revision) is not int or self.revision < 1:
            raise ValueError('Expected profile_id and positive integer revision')
        if self.mode != 'audit' or self.status != 'experimental' or self.strategy not in ('disabled','geometry','geometry_appearance'):
            raise ValueError('Only explicit experimental recovery audit strategies are implemented')
        if not isinstance(self.parameters, AssociationParameters):
            raise ValueError('Invalid association parameters')
        if self.strategy == 'geometry' and self.parameters.appearance_weight != 0:
            raise ValueError('Geometry strategy must have zero appearance weight')

    @classmethod
    def from_dict(cls, value):
        """Esquema independent del diagnòstic i dels antics perfils design-only."""
        fields={'schema_version','task','profile_id','revision','strategy','parameters','mode','status'}
        if not isinstance(value, dict) or set(value) != fields or value['schema_version'] != '1.0' or value['task'] != 'audit_tracking_recovery':
            raise ValueError('Expected complete schema 1.0 audit_tracking_recovery profile')
        params=value['parameters']
        if not isinstance(params, dict) or set(params)-set(AssociationParameters.__dataclass_fields__):
            raise ValueError('Unknown association parameter')
        return cls(**{k:v for k,v in value.items() if k not in ('schema_version','task','parameters')},
                   parameters=AssociationParameters(**params))
