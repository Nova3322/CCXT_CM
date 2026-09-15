"""Read capabilities without promoting unknown, emulated or REST-only features."""

import re
from dataclasses import asdict, dataclass
from typing import Literal

from ccxt import NotSupported

Capability = Literal[True, False, "emulated"] | None


def capability(exchange, method: str) -> Capability:
    for name, value in exchange.has.items():
        snake = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
        snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", snake).lower()
        if name == method or snake == method:
            if value is True or value is False or value is None or value == "emulated":
                return value
            raise ValueError(f"Invalid CCXT capability declaration: {name}={value!r}")
    return None


def require_capabilities(exchange, *methods: str, allow_emulated: bool = False) -> None:
    missing = []
    for method in methods:
        value = capability(exchange, method)
        if value is not True and not (allow_emulated and value == "emulated"):
            missing.append(f"{method}={value!r}")
    if missing:
        raise NotSupported(
            f"{exchange.id}: required capabilities not available: {', '.join(missing)}"
        )


@dataclass(frozen=True)
class SpecialMethod:
    """Metadata only. Invoke the documented exchange method directly, not via a second API."""

    method: str
    description: str
    documentation: str
    private: bool = False
    mutating: bool = False
    returns: str = "raw"


def special_methods(exchange) -> list[dict]:
    declarations = getattr(exchange, "cm_special_methods", ())
    result = []
    seen = set()
    for spec in declarations:
        if not isinstance(spec, SpecialMethod):
            raise TypeError("cm_special_methods must contain SpecialMethod declarations")
        if spec.method in seen or not callable(getattr(exchange, spec.method, None)):
            raise ValueError(f"Invalid or duplicate special method {spec.method!r}")
        if not spec.description or not spec.documentation:
            raise ValueError("Special methods need description and documentation")
        seen.add(spec.method)
        result.append(asdict(spec))
    return result
