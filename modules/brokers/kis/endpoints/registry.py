from __future__ import annotations

from dataclasses import dataclass, field

from modules.brokers.kis.exceptions import KisConfigError, MockNotSupportedError
from modules.brokers.kis.types import Environment, HttpMethod


@dataclass(frozen=True)
class EndpointSpec:
    """Static metadata for one KIS REST endpoint.

    One EndpointSpec corresponds to one row of an Excel API sheet
    in `.agents/kis-skill/resources/`.
    """

    name: str
    method: HttpMethod
    path: str
    tr_id_real: str
    tr_id_mock: str | None = None
    required_params: tuple[str, ...] = ()
    required_headers: tuple[str, ...] = (
        "authorization",
        "appkey",
        "appsecret",
        "tr_id",
    )
    needs_hashkey: bool = False
    supports_tr_cont: bool = False

    def tr_id_for(self, environment: Environment) -> str:
        if environment == "real":
            return self.tr_id_real
        if environment == "mock":
            if self.tr_id_mock is None:
                raise MockNotSupportedError(self.name)
            return self.tr_id_mock
        raise KisConfigError("environment must be one of: real, mock")


@dataclass
class _EndpointRegistry:
    _by_name: dict[str, EndpointSpec] = field(default_factory=dict)

    def register(self, spec: EndpointSpec) -> EndpointSpec:
        if spec.name in self._by_name:
            raise KisConfigError(f"duplicate endpoint registration: {spec.name}")
        self._by_name[spec.name] = spec
        return spec

    def lookup(self, name: str) -> EndpointSpec:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KisConfigError(f"unknown endpoint: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))


_REGISTRY = _EndpointRegistry()


def register(spec: EndpointSpec) -> EndpointSpec:
    return _REGISTRY.register(spec)


def lookup(name: str) -> EndpointSpec:
    return _REGISTRY.lookup(name)


def names() -> tuple[str, ...]:
    return _REGISTRY.names()
