from __future__ import annotations

from dataclasses import dataclass, field

from modules.brokers.kiwoom.exceptions import KiwoomConfigError
from modules.brokers.kiwoom.types import HttpMethod


@dataclass(frozen=True)
class EndpointSpec:
    """Static metadata for one Kiwoom REST endpoint."""

    name: str
    method: HttpMethod
    path: str
    api_id: str
    supports_continuation: bool = False


@dataclass
class _EndpointRegistry:
    _by_name: dict[str, EndpointSpec] = field(default_factory=dict)

    def register(self, spec: EndpointSpec) -> EndpointSpec:
        if spec.name in self._by_name:
            raise KiwoomConfigError(f"duplicate endpoint registration: {spec.name}")
        self._by_name[spec.name] = spec
        return spec

    def lookup(self, name: str) -> EndpointSpec:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KiwoomConfigError(f"unknown endpoint: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))


_REGISTRY = _EndpointRegistry()


def register(spec: EndpointSpec) -> EndpointSpec:
    return _REGISTRY.register(spec)


def lookup(name: str) -> EndpointSpec:
    return _REGISTRY.lookup(name)


def names() -> tuple[str, ...]:
    return _REGISTRY.names()
