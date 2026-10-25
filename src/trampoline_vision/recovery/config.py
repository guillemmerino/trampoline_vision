"""Configuració executable de diagnòstic; les estratègies d'unió són futures."""

from dataclasses import dataclass


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
